#!/usr/bin/env python3
"""Cluster-tier client of trie-pathreconstructor-keybytes-growth--autonomous. Bundled Python driver, protocol 4, one host:port, no retries.
Modes (one JSON object on the last stdout line):
  schema <host> <port>                          ks (SimpleStrategy RF 1); t_big, t_small (k blob PRIMARY KEY, v int) WITH memtable = 'trie'
  load <host> <port> <table> <i0> <i1> <conc>   INSERT keys i0..i1-1; t_big key = 60000 random bytes without 0x00 (seeded by i),
                                                t_small key = 16 bytes, base-255 digits + 1 (no 0x00)
  scan <host> <port> <table> <R> <seconds>      R threads, each looping SELECT token(k), v FROM ks.<table> (fetch size 100) until the deadline
  keylen <table>                                prints the key length of the table (no connection)
Driver loading as in the other stage-4 clients."""
import glob, json, os, random, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-tp33'))
LIB = os.path.join(CASS, 'lib')
BIG_LEN, SMALL_LEN = 60000, 16
NOZERO = bytes([1] + list(range(1, 256)))        # translate table: 0x00 -> 0x01


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


def key_for(table, i):
    if table == 't_big':
        return random.Random(i).randbytes(BIG_LEN).translate(NOZERO)
    d = []
    for _ in range(SMALL_LEN):
        d.append(i % 255 + 1)
        i //= 255
    return bytes(d)


if sys.argv[1] == 'keylen':
    print(BIG_LEN if sys.argv[2] == 't_big' else SMALL_LEN)
    sys.exit(0)

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


def connect(host, port, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=port, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof}, connect_timeout=30)
    return c, c.connect()


def main():
    mode, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    c, s = connect(host, port)
    if mode == 'schema':
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        for t in ('t_big', 't_small'):
            s.execute("CREATE TABLE IF NOT EXISTS ks.%s (k blob PRIMARY KEY, v int) WITH memtable = 'trie'" % t)
        ok = c.control_connection.wait_for_schema_agreement(wait_time=60)
        print(json.dumps({'schema': 'ok', 'agreement': bool(ok)}))
    elif mode == 'load':
        table, i0, i1, conc = sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
        ps = s.prepare('INSERT INTO ks.%s (k, v) VALUES (?, 1)' % table)
        lock, errs, okc = threading.Lock(), [], [0]
        nxt = [i0]
        done = threading.Event()
        active = [0]

        def issue():
            with lock:
                if nxt[0] >= i1:
                    if active[0] == 0:
                        done.set()
                    return
                i = nxt[0]; nxt[0] += 1; active[0] += 1
            f = s.execute_async(ps, (key_for(table, i),))
            f.add_callbacks(callback=on_ok, errback=on_err)

        def on_ok(_):
            with lock:
                okc[0] += 1; active[0] -= 1
            issue()
            with lock:
                if nxt[0] >= i1 and active[0] == 0:
                    done.set()

        def on_err(e):
            with lock:
                errs.append('%s: %s' % (type(e).__name__, str(e)[:200])); active[0] -= 1
                nxt[0] = i1                     # a failed write stops the load: a failure is a reading, not a retry
                if active[0] == 0:
                    done.set()
        t0 = time.time()
        for _ in range(min(conc, i1 - i0)):
            issue()
        done.wait()
        print(json.dumps({'ok': okc[0], 'expected': i1 - i0, 'errors': len(errs), 'first_errors': errs[:3], 'seconds': round(time.time() - t0, 2)}))
    elif mode == 'scan':
        table, R, secs = sys.argv[4], int(sys.argv[5]), float(sys.argv[6])
        deadline = time.time() + secs
        st = {'rows': 0, 'passes': 0, 'errors': []}
        lock = threading.Lock()
        stmt = s.prepare('SELECT token(k), v FROM ks.%s' % table)
        stmt.fetch_size = 100

        def worker():
            while time.time() < deadline:
                n = 0
                try:
                    for _row in s.execute(stmt):
                        n += 1
                        if time.time() >= deadline:
                            break
                except Exception as e:
                    with lock:
                        st['errors'].append('%s: %s' % (type(e).__name__, str(e)[:200]))
                    return
                with lock:
                    st['rows'] += n; st['passes'] += 1
        ths = [threading.Thread(target=worker) for _ in range(R)]
        t0 = time.time()
        for t in ths: t.start()
        for t in ths: t.join()
        print(json.dumps({'rows': st['rows'], 'passes': st['passes'], 'errors': len(st['errors']), 'first_errors': st['errors'][:3], 'seconds': round(time.time() - t0, 2)}))
    c.shutdown()


main()
