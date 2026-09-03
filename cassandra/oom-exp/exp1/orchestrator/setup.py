import sys
from cassandra.cluster import Cluster
from cassandra.policies import RoundRobinPolicy

# Check argument
if len(sys.argv) != 2:
    print(f"Usage: python {sys.argv[0]} <NODE_IP>")
    sys.exit(1)

NODE_IP = sys.argv[1]

cluster = Cluster(
    [NODE_IP],
    load_balancing_policy=RoundRobinPolicy(),
    protocol_version=5
)

session = cluster.connect()

# Create keyspace
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

print(f"Schema created successfully on node {NODE_IP}.")
cluster.shutdown()
