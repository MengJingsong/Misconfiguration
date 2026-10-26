#!/usr/bin/env python3
"""Cluster-tier client (B3c) of hints-HintsBuffer-put-slabCapacity--autonomous. Bundled Python driver,
protocol 4 (large native-v5 requests leave unreturned direct frame buffers, which would mix into a direct-pool reading),
whitelist: the one host given (node A, 127.0.14.1), port 9342, no driver retries. Modes:
  probe <host>                     SELECT release_version FROM system.local
  schema <host> <rf>               CREATE KEYSPACE ks (SimpleStrategy, RF <rf>), ks.small (k bigint PRIMARY KEY, v blob),
                                   ks.big (k int PRIMARY KEY, v blob); waits for schema agreement
  settings <host> <name> ...       rows of system_views.settings for the names on that node (the read-back)
  bulk <host> <n> <bytes> <conc>   n INSERTs into ks.small at CL ONE, k = 0 .. n-1, v = <bytes> random bytes, at most <conc>
                                   in flight; latency mean/p50/p99/max
  big <host> <n> <bytes> <conc>    n INSERTs into ks.big at CL ONE, k = 1 .. n, v = <bytes> random bytes (one buffer made once,
                                   a distinct 8-byte prefix per row), at most <conc> in flight; per-request outcome counts
  hints <host> <n> <bytes> <conc>   n INSERTs into ks.small at CL ANY (the hint workload)\n  one <host> <key> <bytes>         one INSERT into ks.big at CL ANY (the large-hint boundary)\nOne JSON object on stdout. Exit 0 unless the mode itself could not run (a failed write is a reading, not an error).
Driver loading from the max_mutation_size harness's client.py."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-hb'))
LIB = os.path.join(CASS, 'lib')
PORT = int(os.environ.get('HW_NATIVE_PORT', 9342))


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
    c = Cluster([host], port=PORT, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def run_inserts(s, ps, n, first_key, make_val, conc):
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
    for i in range(n):
        sem.acquire()
        t0 = time.time()
        f = s.execute_async(ps, (first_key + i, make_val(i)))
        f.add_callbacks(ok, bad, callback_args=(t0,), errback_args=(t0,))
    for _ in range(conc):
        sem.acquire()
    dur = time.time() - t_start
    nerr = sum(v for k, v in errs.items() if not k.startswith('first_'))
    return {'n': n, 'conc': conc, 'ok': len(lat), 'err': nerr, 'errors': errs, 'seconds': round(dur, 3),
            'rate': round(n / dur, 1),
            'lat_mean_ms': round(1000 * sum(lat) / len(lat), 3) if lat else None,
            'lat_p50_ms': round(1000 * pct(lat, 0.50), 3) if lat else None,
            'lat_p99_ms': round(1000 * pct(lat, 0.99), 3) if lat else None,
            'lat_max_ms': round(1000 * max(lat), 3) if lat else None,
            'ms_start': int(t_start * 1000), 'ms_end': int(time.time() * 1000)}


def main():
    mode, host = sys.argv[1], sys.argv[2]
    if mode == 'probe':
        c, s = connect(host, ConsistencyLevel.ONE)
        print(json.dumps({'release_version': s.execute('SELECT release_version FROM system.local').one()[0]}))
    elif mode == 'schema':
        rf = int(sys.argv[3])
        c, s = connect(host, ConsistencyLevel.ONE)
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': %d}" % rf)
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
        r = run_inserts(s, ps, n, 0, lambda i: os.urandom(size), conc)
        r['bytes'] = size
        print(json.dumps(r))
    elif mode == 'big':
        n, size, conc = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
        c, s = connect(host, ConsistencyLevel.ONE, timeout=300)
        ps = s.prepare('INSERT INTO ks.big (k, v) VALUES (?, ?)')
        base = os.urandom(size)          # incompressible; one buffer, a distinct prefix per row so no two values are identical
        r = run_inserts(s, ps, n, 1, lambda i: i.to_bytes(8, 'big') + base[8:], conc)
        r['bytes'] = size
        print(json.dumps(r))
    elif mode == 'hints':
        # hints <host> <n> <bytes> <conc>: n INSERTs into ks.small at CL ANY, k = 0..n-1, v = <bytes> random bytes
        n, size, conc = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
        c, s = connect(host, ConsistencyLevel.ANY, timeout=120)
        ps = s.prepare('INSERT INTO ks.small (k, v) VALUES (?, ?)')
        base = os.urandom(size)
        r = run_inserts(s, ps, n, 0, lambda i: i.to_bytes(8, 'big') + base[8:], conc)
        r['bytes'] = size
        print(json.dumps(r))
    elif mode == 'one':
        # one <host> <key> <bytes>: one INSERT of <bytes> into ks.big at CL ANY; prints the outcome
        key, size = int(sys.argv[3]), int(sys.argv[4])
        c, s = connect(host, ConsistencyLevel.ANY, timeout=120)
        ps = s.prepare('INSERT INTO ks.big (k, v) VALUES (?, ?)')
        t0 = time.time()
        try:
            s.execute(ps, (key, b'\x07' * size))
            out = {'key': key, 'bytes': size, 'outcome': 'ok'}
        except Exception as e:
            out = {'key': key, 'bytes': size, 'outcome': type(e).__name__, 'message': str(e)[:300]}
        out['ms'] = int(1000 * (time.time() - t0)); out['ms_end'] = int(time.time() * 1000)
        print(json.dumps(out))
    else:
        sys.exit(__doc__)
    c.shutdown()


main()
