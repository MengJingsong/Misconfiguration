#!/usr/bin/env python3
"""Cluster-tier client (B3c) of max_mutation_size-allocateBytes-slabCapacity--autonomous. Bundled Python driver,
**protocol 4** (large native-v5 requests leave unreturned direct frame buffers, the networking_cache_size arm L, which
would mix into a direct-pool reading), whitelist: the one host given (node A, 127.0.0.2), no driver retries. Modes:
  probe <host>                     SELECT release_version FROM system.local
  schema <host>                    CREATE KEYSPACE ks (SimpleStrategy, RF 2), ks.small (k bigint PRIMARY KEY, v blob),
                                   ks.big (k int PRIMARY KEY, v blob); waits for schema agreement
  settings <host> <name> ...       rows of system_views.settings for the names on that node (the read-back)
  bulk <host> <n> <bytes> <conc>   n INSERTs into ks.small at CL ONE, k = 0 .. n-1, v = <bytes> random bytes, at most
                                   <conc> in flight (execute_async); latency of every request kept for mean/p50/p99/max
  one <host> <k> <bytes> <keylog>  one INSERT into ks.big at CL ONE with a <bytes>-byte value, outcome appended to keylog
                                   as "k,bytes,ms_sent,ms_done,ok|err,<error class>: <message>"
One JSON object on stdout. Exit 0 unless the mode itself could not run (a failed write is a reading, not an error).
Driver loading from the internode_max_message_size-inferMessageSize harness's client.py."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1'))
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


def connect(host, cl, timeout=60):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=cl, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def main():
    mode, host = sys.argv[1], sys.argv[2]
    if mode == 'probe':
        c, s = connect(host, ConsistencyLevel.ONE)
        print(json.dumps({'release_version': s.execute('SELECT release_version FROM system.local').one()[0]}))
    elif mode == 'schema':
        c, s = connect(host, ConsistencyLevel.ONE)
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
        s.execute('CREATE TABLE IF NOT EXISTS ks.small (k bigint PRIMARY KEY, v blob)')
        s.execute('CREATE TABLE IF NOT EXISTS ks.big (k int PRIMARY KEY, v blob)')
        ok = c.control_connection.wait_for_schema_agreement(wait_time=60)
        print(json.dumps({'schema': 'ok', 'agreement': bool(ok),
                          'replication': c.metadata.keyspaces['ks'].replication_strategy.export_for_schema()}))
    elif mode == 'settings':
        c, s = connect(host, ConsistencyLevel.ONE)
        res = {}
        for name in sys.argv[3:]:
            r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', [name]).one()
            res[name] = r.value if r else None
        print(json.dumps({'host': host, 'settings': res}))
    elif mode == 'bulk':
        n, size, conc = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
        c, s = connect(host, ConsistencyLevel.ONE, timeout=120)
        ps = s.prepare('INSERT INTO ks.small (k, v) VALUES (?, ?)')
        sem = threading.Semaphore(conc)
        lat, errs = [], {}
        lock = threading.Lock()

        def ok(_, t0):
            lat.append(time.time() - t0)
            sem.release()

        def bad(e, t0):
            with lock:
                k = type(e).__name__
                errs[k] = errs.get(k, 0) + 1
                errs.setdefault('first_' + k, str(e)[:300])
            sem.release()

        t_start = time.time()
        for k in range(n):
            sem.acquire()
            t0 = time.time()
            f = s.execute_async(ps, (k, os.urandom(size)))
            f.add_callbacks(ok, bad, callback_args=(t0,), errback_args=(t0,))
        for _ in range(conc):
            sem.acquire()
        dur = time.time() - t_start
        nerr = sum(v for k, v in errs.items() if not k.startswith('first_'))
        print(json.dumps({'n': n, 'bytes': size, 'conc': conc, 'ok': len(lat), 'err': nerr, 'errors': errs,
                          'seconds': round(dur, 3), 'rate': round(n / dur, 1),
                          'lat_mean_ms': round(1000 * sum(lat) / len(lat), 3) if lat else None,
                          'lat_p50_ms': round(1000 * pct(lat, 0.50), 3) if lat else None,
                          'lat_p99_ms': round(1000 * pct(lat, 0.99), 3) if lat else None,
                          'lat_max_ms': round(1000 * max(lat), 3) if lat else None,
                          'ms_start': int(t_start * 1000), 'ms_end': int(time.time() * 1000)}))
    elif mode == 'one':
        k, size, keylog = int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        c, s = connect(host, ConsistencyLevel.ONE, timeout=120)
        ps = s.prepare('INSERT INTO ks.big (k, v) VALUES (?, ?)')
        v = os.urandom(size)
        t0 = int(time.time() * 1000)
        try:
            s.execute(ps, (k, v))
            res, why = 'ok', ''
        except Exception as e:  # the reading
            res, why = 'err', f'{type(e).__name__}: {str(e)[:300]}'.replace(',', ';').replace('\n', ' ')
        t1 = int(time.time() * 1000)
        with open(keylog, 'a') as log:
            log.write(f'{k},{size},{t0},{t1},{res},{why}\n')
        print(json.dumps({'k': k, 'bytes': size, 'result': res, 'why': why, 'ms_sent': t0, 'ms_done': t1}))
    else:
        sys.exit(__doc__)
    c.shutdown()


main()
