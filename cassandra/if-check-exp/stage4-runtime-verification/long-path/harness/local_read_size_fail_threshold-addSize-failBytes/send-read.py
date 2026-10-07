#!/usr/bin/env python3
"""Cluster-tier client for local_read_size_fail_threshold-addSize-failBytes (case 9c).
Bundled Python driver, protocol 5 (the per-replica failure code is sent only from protocol 5).
Modes:  probe | load <rows> <payload> | read [--fetch-size n] [--trace] "<cql>"
Prints one JSON object on stdout (machine) and a human line on stderr. Exit 0 on OK, 1 on ERR."""
import glob, json, os, sys

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
from cassandra.query import SimpleStatement  # noqa: E402
from cassandra.concurrent import execute_concurrent_with_args  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect():
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    return c, c.connect()


def main():
    a = sys.argv[1:]
    mode = a[0]
    c, s = connect()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'protocol': c.protocol_version}
        elif mode == 'load':
            rows, payload = int(a[1]), int(a[2])
            ps = s.prepare("INSERT INTO ks1.t (pk, ck, v) VALUES (1, ?, ?)")
            val = bytes(payload)
            res = execute_concurrent_with_args(s, ps, [(i, val) for i in range(rows)], concurrency=64, raise_on_first_error=True)
            out = {'ok': True, 'loaded': len(res)}
        elif mode == 'read':
            fetch, trace, i = None, False, 1
            while a[i].startswith('--'):
                if a[i] == '--fetch-size':
                    fetch = int(a[i + 1]); i += 2
                elif a[i] == '--trace':
                    trace = True; i += 1
            q = a[i]
            st = SimpleStatement(q, fetch_size=fetch)
            fut = s.execute_async(st, trace=trace)
            out = {'ok': True, 'cql': q, 'fetch_size': fetch}
            try:
                rs = fut.result()
                n, pages = 0, 1
                while True:
                    n += len(rs.current_rows)
                    if rs.has_more_pages:
                        rs.fetch_next_page(); pages += 1
                    else:
                        break
                out.update(rows=n, pages=pages, warnings=list(fut.warnings or []))
                if trace:
                    try:
                        t = fut.get_query_trace(max_wait=5)
                        out['trace'] = [e.description for e in t.events if 'attempted to read' in e.description or 'local_read_size' in e.description]
                    except Exception as e:  # best effort
                        out['trace_error'] = repr(e)
            except Exception as e:
                out.update(ok=False, error=type(e).__name__, message=str(e)[:400],
                           codes={str(k): v for k, v in (getattr(e, 'error_code_map', None) or {}).items()},
                           failures=getattr(e, 'failures', None), warnings=list(getattr(fut, 'warnings', None) or []))
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
