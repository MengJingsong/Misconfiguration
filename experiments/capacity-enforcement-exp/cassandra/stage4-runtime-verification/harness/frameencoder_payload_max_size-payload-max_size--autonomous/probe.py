import os, sys, time, subprocess
from cassandra.cluster import Cluster
mode, K, WORK = sys.argv[1], int(sys.argv[2]), os.environ['WORK']
c = Cluster(['127.0.0.1'], port=19042, protocol_version=5, compression=False, idle_heartbeat_interval=0)
s = c.connect()
if mode == 'setup':
    s.execute("CREATE KEYSPACE IF NOT EXISTS o124 WITH replication={'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS o124.t (k int PRIMARY KEY, v blob)")
    ins = s.prepare("INSERT INTO o124.t (k, v) VALUES (?, ?)")
    for k in range(8): s.execute(ins, (k, os.urandom(8 << 20)), timeout=60)
    print('setup done'); c.shutdown(); sys.exit(0)
print('pool hosts:', [str(h.endpoint) for h in s.get_pool_state()])   # must be 127.0.0.1:19042 only
for k in range(K): assert len(s.execute("SELECT v FROM o124.t WHERE k=%s", (k,), timeout=60).one().v) == 8 << 20
sample = lambda tag: subprocess.run([os.path.join(WORK, 'sample.sh'), tag], check=False)
sample('baseline')
open(os.path.join(WORK, 'pause'), 'w').close()
futs = [s.execute_async("SELECT v FROM o124.t WHERE k=%s", (k,), timeout=120) for k in range(K)]
for i in range(10): time.sleep(2); sample('paused-%02d' % i)
os.remove(os.path.join(WORK, 'pause'))
sizes = [len(f.result().one().v) for f in futs]; print('result sizes', sizes)
time.sleep(10); sample('released'); c.shutdown()
