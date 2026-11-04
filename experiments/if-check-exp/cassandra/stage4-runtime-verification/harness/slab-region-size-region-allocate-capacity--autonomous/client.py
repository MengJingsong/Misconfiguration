#!/usr/bin/env python3
"""Cluster-tier client (B3c) of slab-region-size-region-allocate-capacity--autonomous. Bundled Python driver, protocol 4
(large native-v5 requests leave unreturned direct frame buffers), whitelist the one host, port 9042.
  probe <host>                     SELECT release_version FROM system.local
  schema <host>                    CREATE KEYSPACE ks (SimpleStrategy RF 1), ks.t (k int PRIMARY KEY, v blob), STCS, uncompressed, no caching
  settings <host> <name> ...       rows of system_views.settings for the names (the read-back)
  big <host> <n> <bytes> <conc> [<rows/s> [<first key>]]   n INSERTs into ks.t at CL ONE, k = first..first+n-1 (rate 0 = unthrottled), v = <bytes> bytes (one random buffer, distinct 8-byte prefix per row),
                                   at most <conc> in flight; per-request outcome counts, latency
One JSON object on stdout. Driver loading from the hints-HintsBuffer-put-slabCapacity harness's client.py."""
import glob, json, os, sys, threading, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/s4-b7-sr7'))
LIB = os.path.join(CASS, 'lib')
PORT = int(os.environ.get('SR_NATIVE_PORT', 9042))


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
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None


def run_inserts(s, ps, n, first_key, make_val, conc, rate=0):
    sem = threading.Semaphore(conc)
    lat, errs, lock = [], {}, threading.Lock()

    def ok(_, t0):
        lat.append(time.time() - t0); sem.release()

    def bad(e, t0):
        with lock:
            k = type(e).__name__
            errs[k] = errs.get(k, 0) + 1
            errs.setdefault('first_' + k, str(e)[:300])
        sem.release()

    t_start = time.time()
    for i in range(n):
        sem.acquire()
        if rate:
            due = t_start + i / rate
            if due > time.time():
                time.sleep(due - time.time())
        t0 = time.time()
        f = s.execute_async(ps, (first_key + i, make_val(i)))
        f.add_callbacks(ok, bad, callback_args=(t0,), errback_args=(t0,))
    for _ in range(conc):
        sem.acquire()
    dur = time.time() - t_start
    nerr = sum(v for k, v in errs.items() if not k.startswith('first_'))
    return {'n': n, 'conc': conc, 'ok': len(lat), 'err': nerr, 'errors': errs, 'seconds': round(dur, 3), 'rate': round(n / dur, 1),
            'lat_mean_ms': round(1000 * sum(lat) / len(lat), 3) if lat else None,
            'lat_p50_ms': round(1000 * pct(lat, 0.5), 3) if lat else None, 'lat_p99_ms': round(1000 * pct(lat, 0.99), 3) if lat else None,
            'lat_max_ms': round(1000 * max(lat), 3) if lat else None, 'ms_start': int(t_start * 1000), 'ms_end': int(time.time() * 1000)}


def main():
    mode, host = sys.argv[1], sys.argv[2]
    if mode == 'probe':
        c, s = connect(host, ConsistencyLevel.ONE)
        print(json.dumps({'release_version': s.execute('SELECT release_version FROM system.local').one()[0]}))
    elif mode == 'schema':
        c, s = connect(host, ConsistencyLevel.ONE)
        s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
        s.execute('CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v blob) WITH compaction = {\'class\': \'SizeTieredCompactionStrategy\'} AND compression = {\'enabled\': \'false\'} AND caching = {\'keys\': \'NONE\', \'rows_per_partition\': \'NONE\'}')
        ok = c.control_connection.wait_for_schema_agreement(wait_time=60)
        print(json.dumps({'schema': 'ok', 'agreement': bool(ok)}))
    elif mode == 'settings':
        c, s = connect(host, ConsistencyLevel.ONE)
        res = {}
        for name in sys.argv[3:]:
            r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', [name]).one()
            res[name] = r.value if r else None
        print(json.dumps({'host': host, 'settings': res}))
    elif mode == 'big':
        n, size, conc = int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
        rate = float(sys.argv[6]) if len(sys.argv) > 6 else 0
        first = int(sys.argv[7]) if len(sys.argv) > 7 else 1
        c, s = connect(host, ConsistencyLevel.ONE, timeout=300)
        ps = s.prepare('INSERT INTO ks.t (k, v) VALUES (?, ?)')
        base = os.urandom(size)
        r = run_inserts(s, ps, n, first, lambda i: (first + i).to_bytes(8, 'big') + base[8:], conc, rate)
        r['bytes'] = size
        print(json.dumps(r))
    else:
        sys.exit(__doc__)
    c.shutdown()


main()
