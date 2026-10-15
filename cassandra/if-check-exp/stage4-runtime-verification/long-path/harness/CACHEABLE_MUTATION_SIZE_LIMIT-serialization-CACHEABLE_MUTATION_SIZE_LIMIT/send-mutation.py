#!/usr/bin/env python3
"""Cluster-tier client for CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT (case 9c, amended 2026-10-14).
Bundled Python driver (lib/cassandra-driver-internal-only-*.zip, loaded as bin/cqlsh.py loads it), protocol 4 (pinned, 9b),
request timeout 180 s, consistency ONE, FallthroughRetryPolicy (a failure reaches the caller with its own class, never retried).
Table <ks>.t for ks1 and <ks>.ctl for ks0: (pk int PRIMARY KEY, v blob). The payload is <bytes> zero bytes.
Modes:  probe | insert [--ks ks0|ks1] <pk> <bytes> | many [--ks ks0|ks1] <first-pk> <n> <bytes> | readback [--ks ks0|ks1] <pk>
`many` issues its n inserts at once (execute_async on one session) and waits for all of them.
Prints one line: OK <json> or ERR <class> <json> (for `many`: OK only if all n are OK; the JSON lists each result with its
completion time). Exit 0 on OK, 1 on ERR."""
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
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import FallthroughRetryPolicy  # noqa: E402

TIMEOUT = 180


def main():
    a = sys.argv[1:]
    ks = 'ks1'
    if len(a) > 2 and a[1] == '--ks':
        ks = a[2]
        a = [a[0]] + a[3:]
    table = f'{ks}.t' if ks == 'ks1' else f'{ks}.ctl'
    mode = a[0]
    prof = ExecutionProfile(request_timeout=TIMEOUT, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    out = {'mode': mode, 'table': table, 'args': a[1:]}
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out.update(release_version=row.release_version, protocol=c.protocol_version)
        elif mode == 'insert':
            pk, n = int(a[1]), int(a[2])
            ps = s.prepare(f"INSERT INTO {table} (pk, v) VALUES (?, ?)")
            t0 = time.time()
            s.execute(ps, (pk, bytes(n)))
            out.update(pk=pk, payload=n, secs=round(time.time() - t0, 3))
        elif mode == 'many':
            first, n, size = int(a[1]), int(a[2]), int(a[3])
            ps = s.prepare(f"INSERT INTO {table} (pk, v) VALUES (?, ?)")
            payload = bytes(size)
            t0 = time.time()
            futs = [(first + i, s.execute_async(ps, (first + i, payload))) for i in range(n)]
            res, errs = [], 0
            for pk, f in futs:
                try:
                    f.result()
                    res.append({'pk': pk, 'ok': True, 'secs': round(time.time() - t0, 3)})
                except Exception as e:
                    errs += 1
                    res.append({'pk': pk, 'ok': False, 'class': type(e).__name__, 'secs': round(time.time() - t0, 3), 'message': str(e)[:300]})
            out.update(first=first, n=n, payload=size, errors=errs, results=res)
            if errs:
                print('ERR ManyFailed %s' % json.dumps(out))
                return 1
        elif mode == 'readback':
            pk = int(a[1])
            row = s.execute(f"SELECT v FROM {table} WHERE pk = %s", (pk,)).one()
            out.update(pk=pk, exists=row is not None, length=(len(row.v) if row is not None and row.v is not None else None))
        else:
            raise SystemExit('unknown mode ' + mode)
        print('OK ' + json.dumps(out))
        return 0
    except Exception as e:
        out.update(message=str(e)[:1500])
        print('ERR %s %s' % (type(e).__name__, json.dumps(out)))
        return 1
    finally:
        c.shutdown()


if __name__ == '__main__':
    sys.exit(main())
