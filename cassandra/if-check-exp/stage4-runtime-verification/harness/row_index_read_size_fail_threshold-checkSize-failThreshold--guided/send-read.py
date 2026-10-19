#!/usr/bin/env python3
"""Cluster-tier client for row_index_read_size_fail_threshold-checkSize-failThreshold (case 9c).
Bundled Python driver, protocol 5. Modes:
  probe | load-ladder <table> <B,B,...> <payload>  (partition k = 1..n gets rows ck 0..B_k-1)
        | load-rows <table> <pk> <from> <to> <payload> | read "<cql>"
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR."""
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


def main():
    a = sys.argv[1:]
    mode = a[0]
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'protocol': c.protocol_version}
        elif mode == 'load-ladder':
            table, ladder, payload = a[1], [int(x) for x in a[2].split(',')], int(a[3])
            ps = s.prepare(f"INSERT INTO {table} (pk, ck, v) VALUES (?, ?, ?)")
            val = bytes(payload)
            args = [(k + 1, i, val) for k, b in enumerate(ladder) for i in range(b)]
            res = execute_concurrent_with_args(s, ps, args, concurrency=64, raise_on_first_error=True)
            out = {'ok': True, 'loaded': len(res), 'per_partition': ladder}
        elif mode == 'load-rows':
            table, pk, lo, hi, payload = a[1], int(a[2]), int(a[3]), int(a[4]), int(a[5])
            ps = s.prepare(f"INSERT INTO {table} (pk, ck, v) VALUES (?, ?, ?)")
            val = bytes(payload)
            res = execute_concurrent_with_args(s, ps, [(pk, i, val) for i in range(lo, hi)], concurrency=64, raise_on_first_error=True)
            out = {'ok': True, 'loaded': len(res)}
        elif mode == 'read':
            q = a[1]
            fut = s.execute_async(SimpleStatement(q))
            out = {'ok': True, 'cql': q}
            try:
                rs = fut.result()
                n = 0
                while True:
                    n += len(rs.current_rows)
                    if rs.has_more_pages:
                        rs.fetch_next_page()
                    else:
                        break
                out.update(rows=n, warnings=list(fut.warnings or []))
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
