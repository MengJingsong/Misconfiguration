#!/usr/bin/env python3
"""Cluster-tier client for hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous (B3c, copied from the hints-Compressed... harness; adds schemaid, native port from EC_NATIVE_PORT). Bundled Python driver
from the clone's lib/ zip, **protocol 4** (large native-v5 requests leave unreturned direct buffers on the node), the one host
given on native port HU_NATIVE_PORT (default 9145), consistency ONE. Adapted from the WRITE_BUFFER_SIZE harness's client.py.
  probe  <host>
  schema <host> <ks> <rf> <chunk_kb|0>   CREATE KEYSPACE <ks> (SimpleStrategy, RF <rf>) and TABLE <ks>.t (pk bigint PRIMARY KEY, v blob);
                                          chunk_kb > 0: WITH compression = LZ4Compressor, chunk_length_in_kb = <chunk_kb>
  drop   <host> <ks>
  write  <host> <ks> <size> <count> <conc> <first_pk> <max_s> <keylog>
                            <count> INSERTs of one random <size>-byte value each (os.urandom, a different value per row), pk = first_pk..,
                            at most <conc> in flight; stops after <max_s> s or 20 consecutive failures. Every pk is appended to <keylog>
                            as "pk,ms_sent,ms_done,ok|err".
  scan   <host> <ks> <count> <conc> <passes> <max_s>   SELECT v for pk 0..count-1, <passes> times in a random order, <conc> in flight
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR."""
import glob, json, os, random, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-ec'))
LIB = os.path.join(CASS, 'lib')
PORT = int(os.environ.get('EC_NATIVE_PORT', 9355))


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
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, timeout=60):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=PORT, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                token_metadata_enabled=False)
    return c, c.connect()


def run_async(s, make_future, count, conc, max_s, on_done):
    lock = threading.Condition()
    st = {'inflight': 0, 'ok': 0, 'err': 0, 'consec': 0, 'errs': []}

    def done(i, sent, ok, exc=None):
        with lock:
            st['inflight'] -= 1
            st['ok' if ok else 'err'] += 1
            st['consec'] = 0 if ok else st['consec'] + 1
            if exc is not None and len(st['errs']) < 5:
                st['errs'].append(repr(exc)[:200])
            on_done(i, sent, ok)
            lock.notify_all()

    t0 = time.time()
    i = 0
    stopped = 'count'
    while i < count:
        if time.time() - t0 >= max_s:
            stopped = 'time'
            break
        with lock:
            while st['inflight'] >= conc:
                lock.wait(1)
            if st['consec'] >= 20:
                stopped = 'failures'
                break
            st['inflight'] += 1
        sent = int(time.time() * 1000)
        f = make_future(i)
        f.add_callbacks(lambda _r, i=i, sent=sent: done(i, sent, True),
                        lambda e, i=i, sent=sent: done(i, sent, False, e))
        i += 1
    with lock:
        while st['inflight'] > 0:
            lock.wait(1)
    el = time.time() - t0
    return i, st, el, stopped


def main():
    a = sys.argv[1:]
    mode, host = a[0], a[1]
    c, s = connect(host)
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version, host_id FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'host_id': str(row.host_id), 'protocol': c.protocol_version}
        elif mode == 'schema':
            ks, rf, chunk = a[2], int(a[3]), int(a[4])
            s.execute(f"CREATE KEYSPACE IF NOT EXISTS {ks} WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': {rf}}}")
            comp = f" WITH compression = {{'class': 'LZ4Compressor', 'chunk_length_in_kb': {chunk}}}" if chunk > 0 else ''
            s.execute(f"CREATE TABLE IF NOT EXISTS {ks}.t (pk bigint PRIMARY KEY, v blob){comp}")
            agreed = c.control_connection.wait_for_schema_agreement(wait_time=30)
            out = {'ok': True, 'schema_agreement': agreed}
        elif mode == 'schemaid':   # schemaid <host> <ks> <rf> <table-uuid>: ks.t (k int PRIMARY KEY, v blob) WITH ID = <uuid> (the unit tier's table)
            ks, rf, tid = a[2], int(a[3]), a[4]
            s.execute(f"CREATE KEYSPACE IF NOT EXISTS {ks} WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': {rf}}}")
            s.execute(f"CREATE TABLE IF NOT EXISTS {ks}.t (k int PRIMARY KEY, v blob) WITH ID = {tid}")
            agreed = c.control_connection.wait_for_schema_agreement(wait_time=30)
            out = {'ok': True, 'schema_agreement': agreed}
        elif mode == 'count':     # count <host> <ks> : rows of ks.t (k int)
            n = s.execute(f"SELECT count(*) AS n FROM {a[2]}.t", timeout=120).one().n
            out = {'ok': True, 'rows': n}
        elif mode == 'drop':
            s.execute(f"DROP KEYSPACE IF EXISTS {a[2]}")
            out = {'ok': True}
        elif mode == 'write':
            ks, size, count, conc, first, max_s, keylog = a[2], int(a[3]), int(a[4]), int(a[5]), int(a[6]), float(a[7]), a[8]
            ps = s.prepare(f"INSERT INTO {ks}.t (pk, v) VALUES (?, ?)")
            log = open(keylog, 'a')
            vals = [os.urandom(size) for _ in range(min(count, 64))]   # random bytes: incompressible; 64 distinct values reused

            def on_done(i, sent, ok):
                log.write(f'{first + i},{sent},{int(time.time() * 1000)},{"ok" if ok else "err"}\n')

            n, st, el, stopped = run_async(s, lambda i: s.execute_async(ps, (first + i, vals[i % len(vals)])), count, conc, max_s, on_done)
            log.close()
            out = {'ok': n > 0, 'target': count, 'written': n, 'succeeded': st['ok'], 'failed': st['err'], 'errors': st['errs'],
                   'size': size, 'conc': conc, 'elapsed_s': round(el, 2), 'stopped_by': stopped}
        elif mode == 'scan':
            ks, count, conc, passes, max_s = a[2], int(a[3]), int(a[4]), int(a[5]), float(a[6])
            ps = s.prepare(f"SELECT v FROM {ks}.t WHERE pk = ?")
            order = [k for _ in range(passes) for k in random.sample(range(count), count)]
            nbytes = [0]

            def on_done(i, sent, ok):
                pass

            def mk(i):
                f = s.execute_async(ps, (order[i],))
                return f

            n, st, el, stopped = run_async(s, mk, len(order), conc, max_s, on_done)
            out = {'ok': n > 0, 'requests': n, 'succeeded': st['ok'], 'failed': st['err'], 'errors': st['errs'], 'conc': conc,
                   'elapsed_s': round(el, 2), 'stopped_by': stopped}
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out.setdefault('elapsed_s', round(time.time() - t0, 3))
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
