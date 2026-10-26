#!/usr/bin/env python3
"""Create ks.t (id bigint primary key, v int) WITHOUT an index and load rows with unique v. Usage: loader.py <tree> <host> <port> <rows>"""
import sys, glob, time
tree, host, port, rows = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect()
s.default_timeout = 120
s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
s.execute("CREATE TABLE ks.t (id bigint PRIMARY KEY, v int)")
ps = s.prepare("INSERT INTO ks.t (id, v) VALUES (?, ?)")
t0 = time.time()
inflight = []
for i in range(rows):
    inflight.append(s.execute_async(ps, (i, i)))
    if len(inflight) >= 256:
        inflight.pop(0).result()
    if (i + 1) % 500000 == 0:
        print('loaded', i + 1, 'rows in %.1f s' % (time.time() - t0), flush=True)
for f in inflight:
    f.result()
print('loaded %d rows with unique v in %.1f s' % (rows, time.time() - t0), flush=True)
cl.shutdown()
