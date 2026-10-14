#!/usr/bin/env python3
"""Cluster-tier client for max_mutation_size-validateSize-MAX_MUTATION_SIZE (case 9c).
Bundled Python driver, protocol 4 (pinned, 9b), request timeout 120 s, consistency ONE.
Modes:  probe | insert <pk> <bytes> | batch logged|unlogged <pk1> <pk2> <bytes-each> | readback <pk> | settings
Prints one line: OK <json> or ERR <class> <json>. Exit 0 on OK, 1 on ERR."""
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
from cassandra.query import BatchStatement, BatchType  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def main():
    a = sys.argv[1:]
    mode = a[0]
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE)
    c = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    out = {'mode': mode, 'args': a[1:]}
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out.update(release_version=row.release_version, protocol=c.protocol_version)
        elif mode == 'settings':
            rows = list(s.execute("SELECT name, value FROM system_views.settings WHERE name = 'max_mutation_size'"))
            out.update(rows=[[r.name, r.value] for r in rows])
        elif mode == 'insert':
            pk, n = int(a[1]), int(a[2])
            ps = s.prepare("INSERT INTO ks1.t (pk, v) VALUES (?, ?)")
            s.execute(ps, (pk, bytes(n)))
            out.update(pk=pk, payload=n)
        elif mode == 'batch':
            kind, pk1, pk2, n = a[1], int(a[2]), int(a[3]), int(a[4])
            ps = s.prepare("INSERT INTO ks1.t (pk, v) VALUES (?, ?)")
            b = BatchStatement(batch_type=BatchType.LOGGED if kind == 'logged' else BatchType.UNLOGGED)
            b.add(ps, (pk1, bytes(n)))
            b.add(ps, (pk2, bytes(n)))
            s.execute(b)
            out.update(kind=kind, pks=[pk1, pk2], payload_each=n)
        elif mode == 'readback':
            pk = int(a[1])
            row = s.execute("SELECT v FROM ks1.t WHERE pk = %s", (pk,)).one()
            out.update(pk=pk, exists=row is not None, length=(len(row.v) if row is not None and row.v is not None else None))
        else:
            raise SystemExit('unknown mode ' + mode)
        print('OK ' + json.dumps(out))
        return 0
    except Exception as e:
        out.update(message=str(e)[:600])
        print('ERR %s %s' % (type(e).__name__, json.dumps(out)))
        return 1
    finally:
        c.shutdown()


if __name__ == '__main__':
    sys.exit(main())
