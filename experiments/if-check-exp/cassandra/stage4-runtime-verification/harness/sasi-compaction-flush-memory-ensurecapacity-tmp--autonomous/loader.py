#!/usr/bin/env python3
"""Load rows [start, start+count) of <ks>.t (id bigint primary key, v text) with a distinct pseudo-random ASCII value of L characters.
Usage: loader.py <tree> <host> <port> <ks> <start> <count> <L>   (the table must exist; the value of row i comes from random.Random(i))"""
import sys, glob, time, random, string
tree, host, port, ks, start, count, L = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect(); s.default_timeout = 120
ps = s.prepare("INSERT INTO %s.t (id, v) VALUES (?, ?)" % ks)
alpha = string.ascii_letters + string.digits
t0 = time.time(); inflight = []
for i in range(start, start + count):
    v = ''.join(random.Random(i).choices(alpha, k=L))
    inflight.append(s.execute_async(ps, (i, v)))
    if len(inflight) >= 128:
        inflight.pop(0).result()
for f in inflight:
    f.result()
print('loaded rows %d..%d (L=%d) in %.1f s' % (start, start + count - 1, L, time.time() - t0), flush=True)
cl.shutdown()
