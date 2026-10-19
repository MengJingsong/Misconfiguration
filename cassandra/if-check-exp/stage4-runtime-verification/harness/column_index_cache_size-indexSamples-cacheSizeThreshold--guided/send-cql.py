#!/usr/bin/env python3
"""Cluster-tier client for column_index_cache_size-indexSamples-cacheSizeThreshold (case 9c, amended 2026-10-14).
Bundled Python driver, protocol 5. Modes:
  probe
  load <table> <pk_from> <pk_to_incl> <rows>   every pk gets rows ck 0..rows-1 with a fresh random 1,024-byte v, written in
                                               single-partition unlogged batches of 32 rows, partitions in pk order
  read <table> <pk_from> <pk_to_incl> <ck>     one point read SELECT ck FROM <table> WHERE pk = ? AND ck = ? per partition
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR."""
import glob, json, os, sys, time

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
from cassandra.query import BatchStatement, BatchType  # noqa: E402
from cassandra.concurrent import execute_concurrent, execute_concurrent_with_args  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

BATCH = 32
PAYLOAD = 1024


def main():
    a = sys.argv[1:]
    mode = a[0]
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'protocol': c.protocol_version}
        elif mode == 'load':
            table, lo, hi, rows = a[1], int(a[2]), int(a[3]), int(a[4])
            ps = s.prepare(f"INSERT INTO {table} (pk, ck, v) VALUES (?, ?, ?)")
            loaded = 0
            for pk in range(lo, hi + 1):
                stmts = []
                for start in range(0, rows, BATCH):
                    b = BatchStatement(batch_type=BatchType.UNLOGGED, consistency_level=ConsistencyLevel.ONE)
                    for ck in range(start, min(rows, start + BATCH)):
                        b.add(ps, (pk, ck, os.urandom(PAYLOAD)))
                    stmts.append((b, ()))
                res = execute_concurrent(s, stmts, concurrency=32, raise_on_first_error=True)
                loaded += rows
            out = {'ok': True, 'loaded_rows': loaded, 'partitions': hi - lo + 1}
        elif mode == 'read':
            table, lo, hi, ck = a[1], int(a[2]), int(a[3]), int(a[4])
            ps = s.prepare(f"SELECT ck FROM {table} WHERE pk = ? AND ck = ?")
            res = execute_concurrent_with_args(s, ps, [(pk, ck) for pk in range(lo, hi + 1)], concurrency=8, raise_on_first_error=False)
            ok = sum(1 for r in res if r.success and len(list(r.result_or_exc)) == 1)
            errs = [repr(r.result_or_exc)[:200] for r in res if not r.success][:3]
            out = {'ok': ok == hi - lo + 1, 'reads': hi - lo + 1, 'rows_found': ok, 'errors': errs}
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out['elapsed_s'] = round(time.time() - t0, 3)
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
