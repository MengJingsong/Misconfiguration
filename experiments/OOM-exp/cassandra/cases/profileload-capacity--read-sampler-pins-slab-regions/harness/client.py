#!/usr/bin/env python3
"""B25 stage-2 admin client (R21's client.py; schema changed for B25 §2.3). Bundled Python driver from $CASSANDRA_HOME/lib,
protocol 4, CL ONE, WhiteListRoundRobinPolicy([host]), schema_metadata_enabled=False, token_metadata_enabled=False, request
timeout 120 s, unprepared statements.
  client.py <host> probe
  client.py <host> settings <name> ...
  client.py <host> schema <K>        CREATE KEYSPACE b25 (SimpleStrategy, RF 1); tables t0 .. t<K-1> and ttail, each
                                     (pk text PRIMARY KEY, v0 .. v8 blob) with shipped table options
One JSON object on stdout."""

import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', '/mydata/s4/b25/cassandra-u')
LIB = os.path.join(CASS, 'lib')


def find_zip(prefix):
    z = glob.glob(os.path.join(LIB, prefix + '*.zip'))
    return max(z) if z else None


cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for lib in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-', 'futures-'):
    z = find_zip(lib)
    if z:
        sys.path.insert(0, z)

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT  # noqa: E402
from cassandra.policies import WhiteListRoundRobinPolicy, FallthroughRetryPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def connect(host, timeout=120):
    prof = ExecutionProfile(request_timeout=timeout, consistency_level=ConsistencyLevel.ONE, retry_policy=FallthroughRetryPolicy(),
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], port=9042, protocol_version=4, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
                schema_metadata_enabled=False, token_metadata_enabled=False,
                control_connection_timeout=60, connect_timeout=30, max_schema_agreement_wait=120)
    return c, c.connect()


def main(a):
    host, cmd = a[0], a[1]
    t0 = time.time()
    out = {'cmd': cmd, 'args': a[2:], 'start_ms': int(t0 * 1000)}
    c, s = connect(host)
    try:
        if cmd == 'probe':
            out['release_version'] = s.execute('SELECT release_version FROM system.local').one()[0]
        elif cmd == 'settings':
            got = {}
            for n in a[2:]:
                r = s.execute('SELECT name, value FROM system_views.settings WHERE name = %s', (n,)).one()
                got[n] = r[1] if r else None
            out['settings'] = got
        elif cmd == 'schema':
            k = int(a[2])
            s.execute("CREATE KEYSPACE b25 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
            cols = ', '.join(f'v{i} blob' for i in range(9))
            for name in [f't{i}' for i in range(k)] + ['ttail']:
                s.execute(f'CREATE TABLE b25.{name} (pk text PRIMARY KEY, {cols})')
            out['agreement'] = c.control_connection.wait_for_schema_agreement()
            out['tables_n'] = len(list(s.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'b25'")))
        else:
            raise SystemExit(__doc__)
    finally:
        try:
            c.shutdown()
        except Exception:
            pass
    out['seconds'] = round(time.time() - t0, 2)
    print(json.dumps(out), flush=True)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
