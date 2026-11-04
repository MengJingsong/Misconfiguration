#!/usr/bin/env python3
"""Cluster-tier client for max_value_size-read-maxValueSize (case 9c).
Bundled Python driver (lib/cassandra-driver-internal-only-*.zip, loaded as bin/cqlsh.py loads it), protocol 4 (pinned, 9b),
request timeout 120 s, consistency ONE. One blob column; the payload is <bytes> zero bytes.
FallthroughRetryPolicy: the driver's default policy retries a ServerError on the next host, which on one node surfaces as
NoHostAvailable; with it the server's error class (ServerError, ReadFailure) reaches the caller unchanged.
Modes:  probe | settings | insert [--table <t>] <pk> <bytes> | readback [--table <t>] <pk>
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
from cassandra import ConsistencyLevel  # noqa: E402
from cassandra.policies import FallthroughRetryPolicy  # noqa: E402


def main():
    a = sys.argv[1:]
    table = 'ks1.t'
    if len(a) > 2 and a[1] == '--table':
        table = a[2] if '.' in a[2] else 'ks1.' + a[2]
        a = [a[0]] + a[3:]
    mode = a[0]
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy())
    c = Cluster(['127.0.0.1'], protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    out = {'mode': mode, 'table': table, 'args': a[1:]}
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out.update(release_version=row.release_version, protocol=c.protocol_version)
        elif mode == 'settings':
            rows = list(s.execute("SELECT name, value FROM system_views.settings WHERE name = 'max_value_size'"))
            out.update(rows=[[r.name, r.value] for r in rows])
        elif mode == 'insert':
            pk, n = int(a[1]), int(a[2])
            ps = s.prepare(f"INSERT INTO {table} (pk, v) VALUES (?, ?)")
            s.execute(ps, (pk, bytes(n)))
            out.update(pk=pk, payload=n)
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
