# B3c driver as filed, with the native port of AM2 (9342). usage: python3 drop_roles.py <cassandra-home> <n> <L>
import sys, glob, os, time
home, n, L = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
z = glob.glob(os.path.join(home, 'lib', 'cassandra-driver-internal-only-*.zip'))[0]
ver = os.path.basename(z)[len('cassandra-driver-internal-only-'):-4]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
c = Cluster(['127.0.0.1'], port=9342, auth_provider=PlainTextAuthProvider('cassandra', 'cassandra'))
s = c.connect()
pad = 'x' * (L - 8)
t0 = time.time()
for i in range(n):
    s.execute("DROP ROLE IF EXISTS '%08d%s'" % (i, pad))
c.shutdown()
print('sent', n, 'seconds %.1f' % (time.time() - t0))
