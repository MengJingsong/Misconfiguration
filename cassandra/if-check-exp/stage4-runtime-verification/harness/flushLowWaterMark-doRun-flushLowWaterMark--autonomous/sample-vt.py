#!/usr/bin/env python3
"""Sampler for flushLowWaterMark-doRun-flushLowWaterMark--autonomous (B3d, amendments A7 and A10: active_connections);
copied from the closed internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous harness,
with three outbound columns added (active_connections, connection_attempts, successful_connection_attempts).
usage: sample-vt.py <host> <inbound|outbound> <interval_s> <stopfile> <out.csv> [once]
Reads system_views.internode_inbound (on B) or internode_outbound (on A) every <interval_s> s until <stopfile> exists,
one row per peer per sample. `once` takes one sample. A virtual-table read is a local client request on the host's native
port (a CQL connection handler, not the internode handlers under test). From the closed sibling's sample-inbound.py."""
import glob, os, sys, time

CASS = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-flw'))
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

COLS = {'inbound': ['using_bytes', 'using_reserve_bytes', 'scheduled_bytes', 'scheduled_count', 'received_count',
                    'received_bytes', 'processed_count', 'throttled_count', 'throttled_nanos', 'expired_count',
                    'error_count'],
        'outbound': ['using_bytes', 'using_reserve_bytes', 'pending_count', 'pending_bytes', 'sent_count', 'sent_bytes',
                     'expired_count', 'error_count', 'overload_count', 'overload_bytes', 'active_connections',
                     'connection_attempts', 'successful_connection_attempts']}


def main():
    host, kind, interval, stopfile, outf = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4], sys.argv[5]
    once = len(sys.argv) > 6 and sys.argv[6] == 'once'
    cols = COLS[kind]
    prof = ExecutionProfile(request_timeout=10, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    q = s.prepare(f'SELECT address, port, ' + ', '.join(cols) + f' FROM system_views.internode_{kind}')
    new = not os.path.exists(outf)
    f = open(outf, 'a')
    if new:
        f.write('ms,address,port,' + ','.join(cols) + '\n')
    n = 0
    try:
        nxt = time.time()
        while once or not os.path.exists(stopfile):
            ms = int(time.time() * 1000)
            try:
                for r in s.execute(q):
                    f.write(f'{ms},{r.address},{r.port},' + ','.join(str(getattr(r, k)) for k in cols) + '\n')
                n += 1
            except Exception as e:  # one missed sample is recorded, not fatal
                f.write(f'{ms},ERROR,{repr(e)[:100]}\n')
            f.flush()
            if once:
                break
            nxt += interval
            time.sleep(max(0.0, nxt - time.time()))
    finally:
        f.close()
        c.shutdown()
    print(f'samples={n}')


main()
