#!/usr/bin/env python3
"""Cluster-tier client of transition-bytes-collector-add-buffer-length--autonomous. Bundled Python driver, protocol 4, one host:port, no retries.
Modes (one JSON object on the last stdout line):
  schema <host> <port>                      ks (SimpleStrategy RF 1); w1..w4 (pk blob, ck int, v text, PRIMARY KEY (pk, ck)) each with an SAI index on v
  load <host> <port> <table> <n> <pklen> <vlen> <conc>
        INSERT partitions i=0..n-1: pk = pklen pseudo-random bytes (seeded by table and i), ck = 0, v = vlen ASCII characters
        ('%08d' % i then 'x'). A write the SAI term-size guardrail rejects (message contains 'exceeds') is COUNTED and the load goes on;
        any other error stops the load.
  read <host> <port> <seconds> <threads> <table>:<n>:<pklen>:<vlen> ...
        threads loop random point reads by pk and SAI queries WHERE v = <stored value> over the given tables until the deadline
  keyof <table> <i> <pklen>                 prints nothing (reserved)
Driver loading as in the other stage-4 clients."""
import glob, json, os, random, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b7-tc'))
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.auth import PlainTextAuthProvider  # noqa: E402


def pk_for(table, i, n):
    return random.Random(f'{table}/{i}').randbytes(n)


def v_for(i, vlen):
    return ('%08d' % i + 'x' * vlen)[:vlen]


def connect(host, port, timeout=120, user='tcw', pw='tcw'):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30,
                auth_provider=PlainTextAuthProvider(user, pw))
    return c, c.connect()


def main():
    mode, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    if mode == 'schema':          # as the default superuser (the role manager creates it about 10 s after start); AllowAll/superusers skip guardrails
        t_end = time.time() + 180
        while True:
            try:
                c, s = connect(host, port, user='cassandra', pw='cassandra'); break
            except Exception as e:
                if time.time() > t_end: raise
                time.sleep(3)
    else:
        c, s = connect(host, port)
    if mode == 'schema':
        s.execute("CREATE ROLE IF NOT EXISTS tcw WITH PASSWORD = 'tcw' AND LOGIN = true")
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        for t in ('w1', 'w2', 'w3', 'w4'):
            s.execute("CREATE TABLE IF NOT EXISTS ks.%s (pk blob, ck int, v text, PRIMARY KEY (pk, ck))" % t)
            s.execute("CREATE CUSTOM INDEX IF NOT EXISTS %s_v ON ks.%s (v) USING 'StorageAttachedIndex'" % (t, t))
        s.execute("GRANT ALL PERMISSIONS ON KEYSPACE ks TO tcw")
        ok = c.control_connection.wait_for_schema_agreement(wait_time=60)
        time.sleep(5)             # permission cache
        print(json.dumps({'schema': 'ok', 'agreement': bool(ok), 'role': 'tcw (ordinary, non-superuser)'}))
    elif mode == 'load':
        table, n, pklen, vlen, conc = sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7]), int(sys.argv[8])
        ps = s.prepare('INSERT INTO ks.%s (pk, ck, v) VALUES (?, 0, ?)' % table)
        lock = threading.Lock()
        st = {'ok': 0, 'rejected': 0, 'other': [], 'first_rejection': None}
        nxt = [0]
        active = [0]
        done = threading.Event()

        def issue():
            with lock:
                if nxt[0] >= n or st['other']:
                    if active[0] == 0:
                        done.set()
                    return
                i = nxt[0]; nxt[0] += 1; active[0] += 1
            f = s.execute_async(ps, (pk_for(table, i, pklen), v_for(i, vlen)))
            f.add_callbacks(callback=on_ok, errback=on_err)

        def on_ok(_):
            with lock:
                st['ok'] += 1; active[0] -= 1
            issue()

        def on_err(e):
            with lock:
                msg = '%s: %s' % (type(e).__name__, str(e)[:300])
                if 'exceeds' in msg:
                    st['rejected'] += 1
                    if st['first_rejection'] is None:
                        st['first_rejection'] = msg
                else:
                    st['other'].append(msg)
                active[0] -= 1
            issue()
        t0 = time.time()
        for _ in range(min(conc, n)):
            issue()
        done.wait()
        print(json.dumps({'table': table, 'ok': st['ok'], 'rejected': st['rejected'], 'expected': n, 'other_errors': len(st['other']),
                          'first_other': st['other'][:2], 'first_rejection': st['first_rejection'], 'seconds': round(time.time() - t0, 2)}))
    elif mode == 'read':
        secs, threads = float(sys.argv[4]), int(sys.argv[5])
        specs = []
        for a in sys.argv[6:]:
            t, n, pklen, vlen = a.split(':')
            if int(n) > 0:
                specs.append((t, int(n), int(pklen), int(vlen)))
        deadline = time.time() + secs
        stm = {t: (s.prepare('SELECT v FROM ks.%s WHERE pk = ?' % t), s.prepare('SELECT pk FROM ks.%s WHERE v = ? LIMIT 1' % t)) for t, *_ in specs}
        stats = {'point': 0, 'sai': 0, 'point_hit': 0, 'sai_hit': 0, 'errors': [], 'by_table': {t: [0, 0, 0, 0] for t, *_ in specs}}
        lock = threading.Lock()

        def worker(seed):
            r = random.Random(seed)
            while time.time() < deadline and specs:
                t, n, pklen, vlen = r.choice(specs)
                i = r.randrange(n)
                try:
                    if r.random() < 0.5:
                        rows = list(s.execute(stm[t][0], (pk_for(t, i, pklen),)))
                        k = 'point'; hit = bool(rows) and rows[0].v == v_for(i, vlen)
                    else:
                        rows = list(s.execute(stm[t][1], (v_for(i, vlen),)))
                        k = 'sai'; hit = bool(rows)
                except Exception as e:
                    with lock:
                        stats['errors'].append('%s: %s' % (type(e).__name__, str(e)[:200]))
                    if len(stats['errors']) > 50:
                        return
                    continue
                with lock:
                    stats[k] += 1; stats[k + '_hit'] += int(hit)
                    bt = stats['by_table'][t]; j = 0 if k == 'point' else 2; bt[j] += 1; bt[j + 1] += int(hit)   # [point, point_hit, sai, sai_hit]
        ths = [threading.Thread(target=worker, args=(1000 + j,)) for j in range(threads)]
        t0 = time.time()
        for t in ths: t.start()
        for t in ths: t.join()
        stats['errors_n'] = len(stats['errors']); stats['first_errors'] = stats.pop('errors')[:3]; stats['seconds'] = round(time.time() - t0, 2)
        print(json.dumps(stats))
    c.shutdown()


main()
