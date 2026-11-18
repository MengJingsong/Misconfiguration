#!/usr/bin/env python3
"""C6 stage-2 client (design §2.5). Bundled Python driver from $CASSANDRA_HOME/lib, protocol 4, CL ONE,
WhiteListRoundRobinPolicy([host]), schema_metadata_enabled=False, token_metadata_enabled=False, request timeout 120 s,
unprepared statements everywhere.
  client.py <host> probe
  client.py <host> settings <name> ...
  client.py <host> tablecount                         count of system_schema.tables rows for keyspace ks
  client.py <host> schema <first> <last> <outdir>     CREATE KEYSPACE IF NOT EXISTS ks ...; CREATE TABLE IF NOT EXISTS ks.t<i>
                                                      one at a time; seconds per 100 tables to <outdir>/schema.csv
  client.py <host> spread <first> <last> <rate> <inflight> <outdir>
                                                      one row (k=1, v=1024 random bytes) into each ks.t<first>..ks.t<last>
  client.py <host> fill <table> <k0> <n> <rate> <inflight> <outdir>
                                                      n rows k=k0.. (v=1024 random bytes) into ks.<table>
spread/fill: progress every second to <outdir>/client.csv (epoch ms, last index sent, ok, err, timeouts, inflight, pass),
every completion to <outdir>/acks.csv (epoch ms, index, status, pass); failed rows are retried in further passes (at most 5
passes in total); stop at the end, after 60 s with no successful write, or after 15 min. One JSON object on stdout."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/c6-w2/cassandra')
LIB = os.path.join(CASS, 'lib')
VALUE = 1024


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-', 'futures-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra import ConsistencyLevel, WriteTimeout, OperationTimedOut  # noqa: E402


def connect(host, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                schema_metadata_enabled=False, token_metadata_enabled=False,
                control_connection_timeout=60, connect_timeout=30, max_schema_agreement_wait=120)
    return c, c.connect()


def write_load(s, items, rate, inflight, outdir, out):
    """items: list of (index, table, k). Rate-paced, at most <inflight> in flight, retry passes."""
    os.makedirs(outdir, exist_ok=True)
    csvf = open(os.path.join(outdir, 'client.csv'), 'a')
    ackf = open(os.path.join(outdir, 'acks.csv'), 'a')
    csvf.write('ms,last_sent,ok,err,timeouts,inflight,pass\n')
    ackf.write('ms,idx,status,pass\n')
    lock = threading.Lock()
    sem = threading.Semaphore(inflight)
    st = {'ok': 0, 'err': 0, 'to': 0, 'last': -1, 'inflight': 0, 'pass': 1, 'last_ok': time.time(), 'failed': [], 'stop': False}
    t_begin = time.time()

    def prog():
        while not st['stop']:
            with lock:
                csvf.write(f"{int(time.time()*1000)},{st['last']},{st['ok']},{st['err']},{st['to']},{st['inflight']},{st['pass']}\n")
                csvf.flush()
            time.sleep(1)

    th = threading.Thread(target=prog, daemon=True)
    th.start()

    def done(item, p, status, e=None):
        with lock:
            st['inflight'] -= 1
            if status == 'ok':
                st['ok'] += 1
                st['last_ok'] = time.time()
            else:
                if status == 'to':
                    st['to'] += 1
                st['err'] += 1
                st['failed'].append(item)
                if e is not None:
                    out.setdefault('first_error', repr(e)[:300])
            ackf.write(f"{int(time.time()*1000)},{item[0]},{status},{p}\n")
        sem.release()

    stopped = None
    todo = list(items)
    for p in range(1, 6):
        st['pass'] = p
        st['failed'] = []
        t0 = time.time()
        for n, item in enumerate(todo):
            while not sem.acquire(timeout=1):
                if time.time() - st['last_ok'] > 60:
                    stopped = 'stall60'
                    break
            if stopped:
                break
            if time.time() - st['last_ok'] > 60:
                sem.release()
                stopped = 'stall60'
                break
            if time.time() - t_begin > 900:
                sem.release()
                stopped = 'limit15min'
                break
            w = t0 + n / rate - time.time()
            if w > 0:
                time.sleep(w)
            idx, table, k = item
            stmt = SimpleStatement(f'INSERT INTO ks.{table} (k, v) VALUES (%s, %s)', consistency_level=ConsistencyLevel.ONE)
            with lock:
                st['inflight'] += 1
                st['last'] = idx
            try:
                f = s.execute_async(stmt, (k, os.urandom(VALUE)))
                f.add_callbacks(lambda r, it=item, pp=p: done(it, pp, 'ok'),
                                lambda e, it=item, pp=p: done(it, pp, 'to' if isinstance(e, (WriteTimeout, OperationTimedOut)) else 'err', e))
            except Exception as e:
                done(item, p, 'err', e)
        # drain in-flight requests of this pass
        t_wait = time.time()
        while st['inflight'] > 0 and time.time() - t_wait < 180:
            time.sleep(0.1)
        if stopped or not st['failed']:
            break
        todo = sorted(st['failed'])
        out.setdefault('retried', []).append(len(todo))
    st['stop'] = True
    th.join(timeout=3)
    with lock:
        csvf.write(f"{int(time.time()*1000)},{st['last']},{st['ok']},{st['err']},{st['to']},{st['inflight']},{st['pass']}\n")
    csvf.close()
    ackf.close()
    out.update(ok=st['ok'], err=st['err'], timeouts=st['to'], passes=st['pass'], unacked_at_end=len(st['failed']),
               stopped=stopped or 'end', inflight_at_end=st['inflight'])


def main(a):
    host, cmd = a[0], a[1]
    t0 = time.time()
    out = {'cmd': cmd, 'args': a[2:], 'start_ms': int(t0 * 1000)}
    c, s = connect(host)
    try:
        if cmd == 'probe':
            out['release_version'] = s.execute('SELECT release_version FROM system.local').one()[0]
        elif cmd == 'settings':
            got = {}
            for n in a[2:]:
                r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', (n,)).one()
                got[n] = r[1] if r else None
            out['settings'] = got
        elif cmd == 'tablecount':
            rows = s.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'ks'")
            out['tables'] = sum(1 for _ in rows)
        elif cmd == 'schema':
            first, last, outdir = int(a[2]), int(a[3]), a[4]
            os.makedirs(outdir, exist_ok=True)
            f = open(os.path.join(outdir, 'schema.csv'), 'a')
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            tb = time.time()
            for i in range(first, last + 1):
                s.execute(f'CREATE TABLE IF NOT EXISTS ks.t{i} (k int PRIMARY KEY, v blob)')
                if (i - first + 1) % 100 == 0:
                    f.write(f'{int(time.time()*1000)},{i},{time.time()-tb:.2f}\n'); f.flush()
                    tb = time.time()
            out['created'] = [first, last]
            out['agreement'] = c.control_connection.wait_for_schema_agreement()
        elif cmd == 'spread':
            first, last, rate, infl, outdir = int(a[2]), int(a[3]), float(a[4]), int(a[5]), a[6]
            write_load(s, [(i, f't{i}', 1) for i in range(first, last + 1)], rate, infl, outdir, out)
        elif cmd == 'fill':
            table, k0, n, rate, infl, outdir = a[2], int(a[3]), int(a[4]), float(a[5]), int(a[6]), a[7]
            write_load(s, [(k, table, k) for k in range(k0, k0 + n)], rate, infl, outdir, out)
        else:
            raise SystemExit(__doc__)
    finally:
        try:
            c.shutdown()
        except Exception:
            pass
    out['seconds'] = round(time.time() - t0, 2)
    print(json.dumps(out), flush=True)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
