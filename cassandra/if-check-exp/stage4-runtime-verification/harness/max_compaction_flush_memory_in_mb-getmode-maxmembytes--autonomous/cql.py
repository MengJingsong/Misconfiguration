#!/usr/bin/env python3
"""Run CQL statements. Usage: cql.py <tree> <host> <port> '<stmt>' ['<stmt>' ...]"""
import sys, glob
tree, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.path.insert(0, glob.glob(tree + '/lib/cassandra-driver-internal-only-*.zip')[0] + '/cassandra-driver-3.29.0')
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
cl = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(), token_metadata_enabled=False, connect_timeout=30)
s = cl.connect(); s.default_timeout = 300
for q in sys.argv[4:]:
    print('CQL', q, flush=True); s.execute(q)
cl.shutdown()
