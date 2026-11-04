#!/usr/bin/env python3
"""Create ks.t with a SASI index and load rows of one value size. Usage: loader.py <tree> <host> <port> <size> <rows> <cap_mb|-> """
import sys, os, glob, random, time
tree, host, port, size, rows, cap = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect()
s.default_timeout = 120
s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
s.execute("CREATE TABLE ks.t (id uuid PRIMARY KEY, v text)")
opts = "'mode':'PREFIX'" + ("" if cap == '-' else ",'max_compaction_flush_memory_in_mb':'%s'" % cap)
s.execute("CREATE CUSTOM INDEX t_v_idx ON ks.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {%s}" % opts)
print('index created with options', opts, flush=True)
rnd = random.Random(size)
pad = ''.join(rnd.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8192))
ps = s.prepare("INSERT INTO ks.t (id, v) VALUES (?, ?)")
import uuid
t0 = time.time()
inflight = []
for i in range(rows):
    off = rnd.randrange(0, 4096)
    v = ('%08d' % i + pad[off:off + size])[:size]
    assert len(v) == size and v.isascii()
    inflight.append(s.execute_async(ps, (uuid.UUID(int=i + 1), v)))
    if len(inflight) >= 64:
        inflight.pop(0).result()
for f in inflight:
    f.result()
print('loaded %d rows of %d bytes in %.1f s' % (rows, size, time.time() - t0), flush=True)
cl.shutdown()
