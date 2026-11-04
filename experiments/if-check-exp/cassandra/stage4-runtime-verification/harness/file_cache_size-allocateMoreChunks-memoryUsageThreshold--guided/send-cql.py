#!/usr/bin/env python3
"""Cluster-tier client for file_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9c, amended 2026-10-14).
Bundled Python driver, protocol 5, request timeout 60 s. Modes:
  probe
  load <pass>              every pk 1..2000 gets rows ck 0..3, each a fresh random 1,024-byte v, one single-partition unlogged
                           batch per pk (64 batches outstanding); <pass> is only logged
  read <C> <seconds>       SELECT * FROM ks1.t WHERE pk = ? with pk uniform in 1..2000, keeping C requests outstanding until
                           <seconds> have passed (no new request after that; the outstanding ones finish)
One JSON object on stdout, a human line on stderr. Exit 0 on OK, 1 on ERR."""
import glob, json, os, random, sys, time

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

PKS = 2000
ROWS = 4
PAYLOAD = 1024


def main():
    a = sys.argv[1:]
    mode = a[0]
    prof = ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE)
    c = Cluster(['127.0.0.1'], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version, 'protocol': c.protocol_version}
        elif mode == 'load':
            ps = s.prepare("INSERT INTO ks1.t (pk, ck, v) VALUES (?, ?, ?)")
            stmts = []
            for pk in range(1, PKS + 1):
                b = BatchStatement(batch_type=BatchType.UNLOGGED, consistency_level=ConsistencyLevel.ONE)
                for ck in range(ROWS):
                    b.add(ps, (pk, ck, os.urandom(PAYLOAD)))
                stmts.append((b, ()))
            res = execute_concurrent(s, stmts, concurrency=64, raise_on_first_error=True)
            ok = sum(1 for r in res if r.success)
            out = {'ok': ok == PKS, 'pass': int(a[1]), 'partitions': ok, 'rows': ok * ROWS}
        elif mode == 'read':
            conc, secs = int(a[1]), float(a[2])
            ps = s.prepare("SELECT * FROM ks1.t WHERE pk = ?")
            deadline = t0 + secs

            def args():
                while time.time() < deadline:
                    yield (random.randint(1, PKS),)

            n = ok = rows_bad = 0
            errs = []
            for success, result in execute_concurrent_with_args(s, ps, args(), concurrency=conc, raise_on_first_error=False, results_generator=True):
                n += 1
                if success:
                    ok += 1
                    if len(list(result)) != ROWS:
                        rows_bad += 1
                elif len(errs) < 3:
                    errs.append(repr(result)[:200])
            el = time.time() - t0
            out = {'ok': ok == n and rows_bad == 0 and n > 0, 'concurrency': conc, 'reads': n, 'succeeded': ok, 'wrong_row_count': rows_bad,
                   'errors': errs, 'reads_per_s': round(n / el, 1)}
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out['elapsed_s'] = round(time.time() - t0, 3)
    print(json.dumps(out))
    print(('OK ' if out.get('ok') else 'ERR ') + json.dumps(out)[:300], file=sys.stderr)
    sys.exit(0 if out.get('ok') else 1)


main()
