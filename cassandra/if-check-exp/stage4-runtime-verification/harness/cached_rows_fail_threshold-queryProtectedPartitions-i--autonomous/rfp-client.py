#!/usr/bin/env python3
"""Cluster-tier client (B3c, amendment C3 of 2026-10-27) of cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.
Driver set-up adapted from harness/paxos_cache_size-close-active--autonomous/pcca-client.py; keyspace, table, payload and modes
are this case's. Bundled Python driver (lib/cassandra-driver-internal-only-*.zip), protocol 5, coordinator pinned to 127.0.0.1
(WhiteListRoundRobinPolicy), token_metadata_enabled=False, heartbeat off, FallthroughRetryPolicy (no retry on another host).
Modes:
  settings            name, value from system_views.settings for the RFP thresholds and the read timeouts
  schema              CREATE KEYSPACE rfp (SimpleStrategy, RF 2); CREATE TABLE rfp.t (k int, c int, v text, pad blob,
                      PRIMARY KEY (k, c)) WITH read_repair = 'NONE'
  load <lo> <hi>      prepared INSERT INTO rfp.t (k, c, v, pad) VALUES (0, ?, 'old', ?) for c in [lo, hi), pad = os.urandom(512), CL ALL
  diverge <lo> <hi>   prepared UPDATE rfp.t SET v = 'new' WHERE k = 0 AND c = ? for c in [lo, hi), CL ONE
  query <CL>          SELECT * FROM rfp.t WHERE v = 'old' ALLOW FILTERING, CL ALL or ONE, fetch_size None (unpaged), timeout 120 s
One JSON object on stdout. Exit 0 when the mode ran (a query error is a reading, reported with ok=false), 2 on a harness error."""
import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME')
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

CONC = 64
PAD = 512
CLS = {'ALL': ConsistencyLevel.ALL, 'ONE': ConsistencyLevel.ONE}


def connect(cl):
    prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']), request_timeout=120,
                            consistency_level=cl, retry_policy=FallthroughRetryPolicy())
    last = None
    for _ in range(5):
        try:
            c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                        token_metadata_enabled=False, idle_heartbeat_interval=0)
            return c, c.connect()
        except Exception as e:  # e.g. ENOBUFS on this Mac
            last = e
            time.sleep(2)
    raise last


def main():
    a = sys.argv[1:]
    mode = a[0]
    cl = CLS[a[1]] if mode == 'query' else (ConsistencyLevel.ONE if mode == 'diverge' else ConsistencyLevel.ALL)
    c, s = connect(cl)
    t0 = time.time()
    out = {'ok': True, 'mode': mode}
    try:
        if mode == 'settings':
            rows = s.execute("SELECT name, value FROM system_views.settings")
            want = ('replica_filtering_protection', 'read_request_timeout', 'range_request_timeout', 'hinted_handoff_enabled',
                    'internode_max_message_size', 'num_tokens', 'auto_bootstrap')
            out['settings'] = {r.name: r.value for r in rows if r.name.startswith(want)}
        elif mode == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS rfp WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}")
            s.execute("CREATE TABLE IF NOT EXISTS rfp.t (k int, c int, v text, pad blob, PRIMARY KEY (k, c)) WITH read_repair = 'NONE'")
            r = s.execute("SELECT read_repair FROM system_schema.tables WHERE keyspace_name = 'rfp' AND table_name = 't'").one()
            out['read_repair'] = r.read_repair
        elif mode in ('load', 'diverge'):
            lo, hi = int(a[1]), int(a[2])
            if mode == 'load':
                ps = s.prepare("INSERT INTO rfp.t (k, c, v, pad) VALUES (0, ?, 'old', ?)")
                args = [(i, os.urandom(PAD)) for i in range(lo, hi)]
            else:
                ps = s.prepare("UPDATE rfp.t SET v = 'new' WHERE k = 0 AND c = ?")
                args = [(i,) for i in range(lo, hi)]
            res = execute_concurrent_with_args(s, ps, args, concurrency=CONC, raise_on_first_error=False)
            errs = [str(r[1])[:200] for r in res if not r[0]]
            out.update({'lo': lo, 'hi': hi, 'applied': len(args) - len(errs), 'errors': len(errs), 'first_error': errs[0] if errs else None})
            out['ok'] = not errs
        elif mode == 'query':
            q = "SELECT * FROM rfp.t WHERE v = 'old' ALLOW FILTERING"
            try:
                from cassandra.query import SimpleStatement
                rs = s.execute(SimpleStatement(q, fetch_size=None, consistency_level=cl), timeout=120)
                n = 0
                for _ in rs:
                    n += 1
                out.update({'cl': a[1], 'rows': n, 'warnings': rs.response_future.warnings})
            except Exception as e:
                out.update({'ok': False, 'cl': a[1], 'error_class': type(e).__module__ + '.' + type(e).__name__,
                            'error': str(e)[:600]})
        else:
            raise ValueError(mode)
    except Exception as e:
        out.update({'ok': False, 'harness_error': repr(e)[:600]})
        out['elapsed_s'] = round(time.time() - t0, 3)
        print(json.dumps(out))
        c.shutdown()
        return 2
    out['elapsed_s'] = round(time.time() - t0, 3)
    print(json.dumps(out, default=str))
    c.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
