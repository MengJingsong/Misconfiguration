#!/usr/bin/env python3
"""Stage 4, internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes, case 9c/9d: the poller.
usage: sample-outbound.py <out.csv> [--host 127.0.0.2] [--interval 0.25] [--stop-file <path>]
Reads system_views.internode_outbound on ONE node (the coordinator the driver is pinned to, S) every <interval> seconds with the bundled
Python driver (protocol 5) and appends one row per peer per sample to <out.csv>: ts_ms (epoch), peer, pending_bytes, using_reserve_bytes,
pending_count, sent_count, expired_count, overload_count, overload_bytes, error_count, active_connections.
pending_bytes is the SUM of the peer's three links (the large link plus a few small messages); using_reserve_bytes is the peer's reserve in use.
Stops on SIGTERM/SIGINT or when the stop file appears. Never writes anything to the node."""
import argparse, csv, glob, os, signal, sys, time

ap = argparse.ArgumentParser()
ap.add_argument('out'); ap.add_argument('--host', default='127.0.0.2'); ap.add_argument('--interval', type=float, default=0.25)
ap.add_argument('--stop-file'); ap.add_argument('--clone', default=os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-run1')))
a = ap.parse_args()

lib = os.path.join(a.clone, 'lib')
def find_zip(prefix):
    z = glob.glob(os.path.join(lib, prefix + '*.zip'))
    return max(z) if z else None
cql = find_zip('cassandra-driver-internal-only-')
ver = os.path.splitext(os.path.basename(cql))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(cql, 'cassandra-driver-' + ver))
for pre in ('pure_sasl-', 'wcwidth-', 'pyasyncore-'):
    z = find_zip(pre)
    if z:
        sys.path.insert(0, z)
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel

stop = False
def _stop(*_):
    global stop
    stop = True
signal.signal(signal.SIGTERM, _stop); signal.signal(signal.SIGINT, _stop)

prof = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy([a.host]), request_timeout=10, consistency_level=ConsistencyLevel.ONE)
cl = Cluster([a.host], protocol_version=5, execution_profiles={EXEC_PROFILE_DEFAULT: prof})
s = cl.connect()
s.execute('SELECT address FROM system_views.internode_outbound')          # warm up: a client connection reads system tables
COLS = 'address, port, pending_bytes, using_reserve_bytes, pending_count, sent_count, expired_count, overload_count, overload_bytes, error_count, active_connections'
q = s.prepare('SELECT ' + COLS + ' FROM system_views.internode_outbound')
w = csv.writer(open(a.out, 'a', buffering=1))
if os.path.getsize(a.out) == 0:
    w.writerow(['ts_ms', 'peer', 'pending_bytes', 'using_reserve_bytes', 'pending_count', 'sent_count', 'expired_count', 'overload_count', 'overload_bytes',
                'error_count', 'active_connections'])
nxt = time.time()
while not stop and not (a.stop_file and os.path.exists(a.stop_file)):
    t = int(time.time() * 1000)
    try:
        for r in s.execute(q):
            w.writerow([t, '%s:%d' % (r.address, r.port), r.pending_bytes, r.using_reserve_bytes, r.pending_count, r.sent_count, r.expired_count,
                        r.overload_count, r.overload_bytes, r.error_count, r.active_connections])
    except Exception as e:
        w.writerow([t, 'ERROR', repr(e)[:120]] + [''] * 8)
    nxt += a.interval
    time.sleep(max(0, nxt - time.time()))
cl.shutdown()
