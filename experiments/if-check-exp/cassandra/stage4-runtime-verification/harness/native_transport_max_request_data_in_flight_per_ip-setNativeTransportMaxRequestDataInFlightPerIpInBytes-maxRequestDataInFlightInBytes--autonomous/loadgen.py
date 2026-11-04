#!/usr/bin/env python3
"""Cluster-tier client (case file B3c, audit amendment R14).
usage: loadgen.py setup HOST PORT
       loadgen.py load HOST PORT PROTO THREADS PER_THREAD BLOB_BYTES [SRC2 THREADS2]
Every worker has its own Cluster (one pool connection plus the control connection), a synchronous loop of
INSERT INTO ks.t (k, v) VALUES (?, ?) with a BLOB_BYTES blob, so at most THREADS (+THREADS2) requests are in flight.
Workers 0..THREADS-1 connect from the default source address; the next THREADS2 workers bind SRC2 as their source.
CASSANDRA_HOME must point at the working tree (the bundled driver is imported from lib/)."""
import glob, os, socket, sys, threading, time, collections
home = os.environ['CASSANDRA_HOME']
z = glob.glob(os.path.join(home, 'lib', 'cassandra-driver-internal-only-*.zip'))[0]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + os.path.basename(z)[len('cassandra-driver-internal-only-'):-4]))
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.io.asyncorereactor import AsyncoreConnection

def src_conn(ip):
    class _S:                       # socket module stand-in whose sockets bind the source address first
        def __getattr__(self, n): return getattr(socket, n)
        def socket(self, *a, **k):
            s = socket.socket(*a, **k); s.bind((ip, 0)); return s
    class Conn(AsyncoreConnection):
        _socket_impl = _S()
    return Conn

def cluster(host, port, proto, conn=None):
    prof = ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=600)
    kw = dict(contact_points=[host], port=port, protocol_version=proto, execution_profiles={EXEC_PROFILE_DEFAULT: prof},
              token_metadata_enabled=False, connect_timeout=60, control_connection_timeout=60, idle_heartbeat_interval=0, executor_threads=2)
    if conn: kw['connection_class'] = conn
    return Cluster(**kw)

if sys.argv[1] == 'setup':
    c = cluster(sys.argv[2], int(sys.argv[3]), 4); s = c.connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS ks.t (k int PRIMARY KEY, v blob)")
    print('setup ok'); c.shutdown(); sys.exit(0)

H, P, PROTO, N, PER, BLOB = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
SRC2 = sys.argv[8] if len(sys.argv) > 8 else None; N2 = int(sys.argv[9]) if len(sys.argv) > 9 else 0
blob = b'\xab' * BLOB
res = collections.Counter(); lock = threading.Lock(); go = threading.Event(); done = threading.Event()
def worker(i):
    try:
        c = cluster(H, P, PROTO, src_conn(SRC2) if (SRC2 and i >= N) else None); s = c.connect()
        prep = s.prepare("INSERT INTO ks.t (k, v) VALUES (?, ?)")
        with lock: res['connected'] += 1
    except Exception as e:
        with lock: res['connect_err:' + type(e).__name__] += 1
        print('CONNECT_ERR', i, repr(e)[:300], flush=True); return
    go.wait()
    for j in range(PER):
        try:
            s.execute(prep, (i, blob))
            with lock: res['ok'] += 1
        except Exception as e:
            with lock: res['err:' + type(e).__name__] += 1; print('ERR', i, repr(e)[:300], flush=True)
    with lock: res['finished'] += 1
    c.shutdown()
ts = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(N + N2)]
[t.start() for t in ts]
# connection phase: every worker must connect within 240 s, otherwise the run is invalid (exit 3, no load sent)
dl = time.time() + 240
while time.time() < dl and res['connected'] < N + N2: time.sleep(0.5)
if res['connected'] < N + N2:
    print('FAIL_CONNECT connected=%d of %d' % (res['connected'], N + N2), dict(res), flush=True); os._exit(3)
print('READY connected=%d' % res['connected'], flush=True)
t0 = time.time(); print('LOAD_START_MS', int(t0 * 1000), flush=True); go.set()
while res['finished'] + sum(v for k, v in res.items() if k.startswith('connect_err')) < N + N2: time.sleep(0.5)
print('RESULT', 'proto=%d threads=%d+%d per=%d blob=%d secs=%.1f' % (PROTO, N, N2, PER, BLOB, time.time() - t0), dict(res), flush=True)
os._exit(0)
