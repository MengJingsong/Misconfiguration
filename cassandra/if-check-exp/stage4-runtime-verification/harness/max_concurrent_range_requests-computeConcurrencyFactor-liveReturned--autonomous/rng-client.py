#!/usr/bin/env python3
"""Cluster-tier client (B3c, amendment C4 of 2026-10-27) of max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.
Driver set-up adapted from harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/rfp-client.py; keyspace, table,
payload and modes are this case's. Bundled Python driver (lib/cassandra-driver-internal-only-*.zip), protocol 5, coordinator pinned to
127.0.0.1 (WhiteListRoundRobinPolicy), token_metadata_enabled=False, heartbeat off, FallthroughRetryPolicy, request timeout 60 s.
Modes:
  schema                 CREATE KEYSPACE rng (SimpleStrategy, RF 1); CREATE TABLE rng.t (k bigint PRIMARY KEY, pad blob)
  load <n> <lo> <hi>     keys = the first n distinct values of random.Random(20261027).getrandbits(64) - 2**63; inserts keys[lo:hi]
                         with pad = os.urandom(2048), prepared INSERT, CL ONE, concurrency 64
  query <fetch> <trace> <count> <gap_s>
                         SELECT * FROM rng.t, CL ONE, fetch_size <fetch>; reads only the first page (current_rows); <count> queries
                         <gap_s> apart; trace=1 also reads the trace events (after a 5 s wait). One JSON line per query.
Exit 0 when the mode ran (a query error is a reading, reported with ok=false), 2 on a harness error."""
import glob, json, os, random, sys, time

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
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

PAD = 2048
SEED = 20261027


def connect():
    prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy(['127.0.0.1']), request_timeout=60,
                            consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
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


def keys(n):
    r = random.Random(SEED)
    seen, out = set(), []
    while len(out) < n:
        k = r.getrandbits(64) - 2 ** 63
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def main():
    a = sys.argv[1:]
    mode = a[0]
    c, s = connect()
    rc = 0
    try:
        if mode == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS rng WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            s.execute("CREATE TABLE IF NOT EXISTS rng.t (k bigint PRIMARY KEY, pad blob)")
            r = s.execute("SELECT replication FROM system_schema.keyspaces WHERE keyspace_name = 'rng'").one()
            print(json.dumps({'ok': True, 'mode': mode, 'replication': dict(r.replication)}))
        elif mode == 'load':
            n, lo, hi = int(a[1]), int(a[2]), int(a[3])
            ks = keys(n)[lo:hi]
            ps = s.prepare("INSERT INTO rng.t (k, pad) VALUES (?, ?)")
            t0 = time.time()
            res = execute_concurrent_with_args(s, ps, [(k, os.urandom(PAD)) for k in ks], concurrency=64, raise_on_first_error=False)
            errs = [str(r[1])[:200] for r in res if not r[0]]
            print(json.dumps({'ok': not errs, 'mode': mode, 'n': n, 'lo': lo, 'hi': hi, 'applied': len(ks) - len(errs),
                              'errors': len(errs), 'first_error': errs[0] if errs else None, 'elapsed_s': round(time.time() - t0, 2)}))
        elif mode == 'query':
            fetch, trace, count, gap = int(a[1]), a[2] == '1', int(a[3]), float(a[4])
            for i in range(count):
                if i:
                    time.sleep(gap)
                out = {'mode': mode, 'i': i, 'fetch': fetch, 'trace': trace, 'start_ms': int(time.time() * 1000)}
                t0 = time.time()
                try:
                    rs = s.execute(SimpleStatement("SELECT * FROM rng.t", fetch_size=fetch), trace=trace)
                    rows = rs.current_rows
                    out.update({'ok': True, 'rows': len(rows), 'has_more_pages': rs.has_more_pages,
                                'pad_len_min': min(len(r.pad) for r in rows) if rows else None,
                                'elapsed_s': round(time.time() - t0, 3)})
                    del rows
                    if trace:
                        time.sleep(5)
                        tr = rs.get_query_trace(max_wait_sec=20)
                        out['trace_events'] = [e.description for e in tr.events]
                        out['coordinator'] = str(tr.coordinator)
                    del rs
                except Exception as e:
                    out.update({'ok': False, 'error_class': type(e).__name__, 'error': str(e)[:600],
                                'elapsed_s': round(time.time() - t0, 3)})
                print(json.dumps(out, default=str), flush=True)
        else:
            raise ValueError(mode)
    except Exception as e:
        print(json.dumps({'ok': False, 'mode': mode, 'harness_error': repr(e)[:600]}))
        rc = 2
    c.shutdown()
    return rc


if __name__ == '__main__':
    sys.exit(main())
