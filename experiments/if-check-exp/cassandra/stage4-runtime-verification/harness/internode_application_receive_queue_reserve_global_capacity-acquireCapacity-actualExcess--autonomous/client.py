#!/usr/bin/env python3
"""Cluster-tier client for internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous (B3e
step 3). Bundled Python driver (loaded from the clone's lib/ zip), protocol 5, whitelist: the one host given.
  probe <host>          SELECT release_version FROM system.local
  schema <host>         CREATE KEYSPACE ks (NetworkTopologyStrategy, 'datacenter1': 2) and TABLE ks.t (pk bigint PRIMARY
                        KEY, v blob); waits for schema agreement
One JSON object on stdout. Exit 0 on OK, 1 on ERR. From the the closed sibling harness (copied 2026-10-22)."""
import glob, json, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-rsv'))
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
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402


def main():
    mode, host = sys.argv[1], sys.argv[2]
    prof = ExecutionProfile(request_timeout=120, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    t0 = time.time()
    try:
        if mode == 'probe':
            row = s.execute("SELECT release_version FROM system.local").one()
            out = {'ok': True, 'release_version': row.release_version}
        elif mode == 'schema':
            s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = "
                      "{'class': 'NetworkTopologyStrategy', 'datacenter1': 2}")
            s.execute("CREATE TABLE IF NOT EXISTS ks.t (pk bigint PRIMARY KEY, v blob)")
            agreed = c.control_connection.wait_for_schema_agreement(wait_time=60)
            out = {'ok': bool(agreed), 'schema_agreement': agreed}
        else:
            raise SystemExit('unknown mode')
    finally:
        c.shutdown()
    out['elapsed_s'] = round(time.time() - t0, 3)
    print(json.dumps(out))
    sys.exit(0 if out.get('ok') else 1)


main()
