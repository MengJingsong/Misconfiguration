# Case B3c loader, amendment A3 (driver package path inside the bundled zip) and A1 (paths).
import os, subprocess, sys, glob, time
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
z = glob.glob(W + '/s3probe/v64/lib/cassandra-driver-internal-only-*.zip')[0]
ver = os.path.basename(z)[len('cassandra-driver-internal-only-'):-len('.zip')]
sys.path.insert(0, z + '/cassandra-driver-' + ver)
from cassandra.cluster import Cluster
v, K, PARTS, ROWS, VSIZE = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
import socket
# harness change H4 (2026-11-25): TCP_NODELAY on the client socket. Without it each synchronous insert waited
# ~40-60 ms (Nagle / delayed ACK on loopback), so an 8 KiB-partition load took ~48 min. Same rows, same flush points.
s = Cluster(['127.0.0.1'], sockopts=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]).connect()
ins = s.prepare("INSERT INTO p.t (pk, ck, v) VALUES (?, ?, ?)")
nt = W + '/s3probe/%s/bin/nodetool' % v
for k in range(K):
    for p in range(PARTS):
        for c in range(ROWS):
            s.execute(ins, ('s%d-p%d' % (k, p), c, os.urandom(VSIZE)))
    subprocess.check_call([nt, 'flush', 'p', 't'])
    print('%d flushed k=%d (%d partitions x %d rows x %d B)' % (int(time.time()), k, PARTS, ROWS, VSIZE), flush=True)
