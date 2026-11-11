#!/usr/bin/env python3
"""Load incompressible rows into ks.t on node A. Usage: loader.py <tree> <host> <port> <chunk_kb> <ratio> <rows> <rowbytes>"""
import sys, os, glob
tree, host, port, chunk_kb, ratio, rows, rowbytes = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect()
s.default_timeout = 120
s.execute("CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
comp = "{'class':'LZ4Compressor','chunk_length_in_kb':'%s'" % chunk_kb
if ratio != '0':
    comp += ",'min_compress_ratio':'%s'" % ratio
comp += "}"
s.execute("CREATE TABLE ks.t (id int PRIMARY KEY, v blob) WITH compression = " + comp)
print('table created with compression', comp, flush=True)
ps = s.prepare("INSERT INTO ks.t (id, v) VALUES (?, ?)")
inflight = []
for i in range(rows):
    inflight.append(s.execute_async(ps, (i, os.urandom(rowbytes))))
    if len(inflight) >= 8:
        inflight.pop(0).result()
for f in inflight:
    f.result()
print('loaded', rows, 'rows of', rowbytes, 'bytes', flush=True)
cl.shutdown()
