# 00_setup.py
from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy

NODE_IP = "128.110.216.213"

cluster = Cluster(
    [NODE_IP],
    load_balancing_policy=RoundRobinPolicy(),
    protocol_version=5
)
session = cluster.connect()

session.execute("""
    CREATE KEYSPACE IF NOT EXISTS oomtest
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
""")
session.set_keyspace('oomtest')

# General-purpose wide-row table
session.execute("""
    CREATE TABLE IF NOT EXISTS wide (
        pk  int,
        ck  int,
        val blob,
        PRIMARY KEY (pk, ck)
    )
""")

# Dedicated table for huge-partition test
session.execute("""
    CREATE TABLE IF NOT EXISTS bigpart (
        pk  int,
        ck  int,
        val blob,
        PRIMARY KEY (pk, ck)
    )
""")

print("Schema created successfully.")
cluster.shutdown()
