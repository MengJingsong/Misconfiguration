#!/usr/bin/env python3
"""write_blobs.py <ip> <port> <N> <blob-bytes> <create-schema 0|1> : protocol 4, CL ANY, 6 MiB random blobs."""
import sys, os, time
sys.path.insert(0, os.path.expanduser("~/s4-fc/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0"))
from cassandra.cluster import Cluster
from cassandra.policies import WhiteListRoundRobinPolicy
from cassandra import ConsistencyLevel
ip, port, N, size, create = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
cl = Cluster([ip], port=port, protocol_version=4, load_balancing_policy=WhiteListRoundRobinPolicy([ip]), connect_timeout=30, max_schema_agreement_wait=60)
s = cl.connect()
s.default_timeout = 60
if create:
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':3}")
    s.execute("CREATE TABLE IF NOT EXISTS ks.t (id int PRIMARY KEY, b blob)")
    print("schema created", flush=True)
    cl.shutdown(); sys.exit(0)
ps = s.prepare("INSERT INTO ks.t (id, b) VALUES (?, ?)")
ps.consistency_level = ConsistencyLevel.ANY
t0 = time.time()
for i in range(N):
    s.execute(ps, (i, os.urandom(size)))
    if i % 20 == 0: print(f"written {i+1}/{N} t={time.time()-t0:.1f}s", flush=True)
print(f"done {N} rows of {size} bytes in {time.time()-t0:.1f}s", flush=True)
cl.shutdown()
