#!/usr/bin/env python3
"""Sampler for internode_application_receive_queue_capacity-acquireCapacity-queueCapacity (case 9c/9d, amended
2026-10-14).
usage: sample-inbound.py <host> <interval_s> <stopfile> <out.csv> [once]
Reads system_views.internode_inbound on <host> (R) every <interval_s> seconds until <stopfile> exists, one row per peer
per sample: ms,address,port,using_bytes,using_reserve_bytes,scheduled_bytes,scheduled_count,received_count,
processed_count,throttled_count,throttled_nanos,expired_count,error_count. `once` takes one sample and exits.
A virtual-table read is a local client request on R's native port; it goes through a CQL connection handler, not the
internode handlers under test."""
import glob, os, sys, time

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
from cassandra.policies import WhiteListRoundRobinPolicy  # noqa: E402
from cassandra import ConsistencyLevel  # noqa: E402

COLS = ['using_bytes', 'using_reserve_bytes', 'scheduled_bytes', 'scheduled_count', 'received_count', 'processed_count',
        'throttled_count', 'throttled_nanos', 'expired_count', 'error_count']


def main():
    host, interval, stopfile, outf = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
    once = len(sys.argv) > 5 and sys.argv[5] == 'once'
    prof = ExecutionProfile(request_timeout=10, consistency_level=ConsistencyLevel.ONE,
                            load_balancing_policy=WhiteListRoundRobinPolicy([host]))
    c = Cluster([host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
    s = c.connect()
    q = s.prepare('SELECT address, port, ' + ', '.join(COLS) + ' FROM system_views.internode_inbound')
    new = not os.path.exists(outf)
    f = open(outf, 'a')
    if new:
        f.write('ms,address,port,' + ','.join(COLS) + '\n')
    n = 0
    try:
        nxt = time.time()
        while once or not os.path.exists(stopfile):
            ms = int(time.time() * 1000)
            try:
                for r in s.execute(q):
                    f.write(f'{ms},{r.address},{r.port},' + ','.join(str(getattr(r, k)) for k in COLS) + '\n')
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
