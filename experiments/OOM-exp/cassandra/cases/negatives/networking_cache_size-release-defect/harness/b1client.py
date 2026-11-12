#!/usr/bin/env python3
"""B1 client (apt138). Bundled Python driver from $CASSANDRA_HOME/lib (default ~/cassandra-c1).
usage:
  b1client.py schema                         protocol 4: keyspace b1 (RF 1), table b1.t (pk int PRIMARY KEY, v blob)
  b1client.py cycle <proto> <bytes> <n> <window> <seed> [seconds]
      one connection, prepared INSERT INTO b1.t (pk, v) VALUES (?, ?), pk = i % 64, a fresh random value of <bytes>
      per request, at most <window> in flight; stops after n requests (or after [seconds] if given, n then a cap).
      Prints the negotiated protocol, the server-side view from system_views.clients, acks, errors, MB/s.
No compression (no lz4 module on the node); the driver is told compression=False anyway."""
import glob, os, random, sys, threading, time

C = os.environ.get('CASSANDRA_HOME', os.path.expanduser('~/cassandra-c1'))
lib = os.path.join(C, 'lib')
z = max(glob.glob(os.path.join(lib, 'cassandra-driver-internal-only-*.zip')))
ver = os.path.splitext(os.path.basename(z))[0][len('cassandra-driver-internal-only-'):]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
for pre in ('pure_sasl-', 'wcwidth-', 'pyasyncore-', 'geomet-'):
    zz = glob.glob(os.path.join(lib, pre + '*.zip'))
    if zz:
        sys.path.insert(0, max(zz))
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel

HOST = os.environ.get('B1_HOST', '10.10.1.1')


def cluster(proto):
    return Cluster([HOST], protocol_version=proto, compression=False,
                   execution_profiles={EXEC_PROFILE_DEFAULT: ExecutionProfile(
                       load_balancing_policy=WhiteListRoundRobinPolicy([HOST]),
                       request_timeout=60, consistency_level=ConsistencyLevel.ONE)})


cmd = sys.argv[1]
if cmd == 'schema':
    cl = cluster(4)
    s = cl.connect()
    s.execute("CREATE KEYSPACE IF NOT EXISTS b1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    s.execute('CREATE TABLE IF NOT EXISTS b1.t (pk int PRIMARY KEY, v blob)')
    print('schema ok proto', cl.protocol_version)
    cl.shutdown()
elif cmd == 'cycle':
    proto, nbytes, n, window, seed = (int(x) for x in sys.argv[2:7])
    secs = float(sys.argv[7]) if len(sys.argv) > 7 else None
    cl = cluster(proto)
    s = cl.connect()
    try:
        rows = list(s.execute('SELECT protocol_version, address FROM system_views.clients'))
        srv = sorted(set(r.protocol_version for r in rows))
    except Exception as e:
        srv = 'n/a(%s)' % type(e).__name__
    ps = s.prepare('INSERT INTO b1.t (pk, v) VALUES (?, ?)')
    rnd = random.Random(seed)
    sem = threading.Semaphore(window)
    lock = threading.Lock()
    st = {'ok': 0, 'err': 0, 'firsterr': None}
    done = threading.Event()

    def cb_ok(_):
        with lock:
            st['ok'] += 1
        sem.release()

    def cb_err(e):
        with lock:
            st['err'] += 1
            if st['firsterr'] is None:
                st['firsterr'] = repr(e)[:300]
        sem.release()

    t0 = time.time()
    sent = 0
    while sent < n and (secs is None or time.time() - t0 < secs):
        sem.acquire()
        f = s.execute_async(ps, (sent % 64, rnd.randbytes(nbytes)))
        f.add_callbacks(cb_ok, cb_err)
        sent += 1
    for _ in range(window):
        sem.acquire()
    dt = time.time() - t0
    print('cycle proto_client=%d proto_server=%s sent=%d ok=%d err=%d secs=%.1f MBps=%.1f firsterr=%s' % (
        cl.protocol_version, srv, sent, st['ok'], st['err'], dt, st['ok'] * nbytes / dt / 1e6, st['firsterr']))
    cl.shutdown()
