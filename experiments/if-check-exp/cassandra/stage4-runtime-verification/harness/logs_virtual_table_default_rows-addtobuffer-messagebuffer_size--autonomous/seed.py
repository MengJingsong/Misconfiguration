#!/usr/bin/env python3
"""Seed the schema for B3a/B3e step 1: 40 keyspaces x 25 tables (RF 1, SimpleStrategy). usage: seed.py <lib dir>"""
import glob, os, sys, time
for z in glob.glob(os.path.join(sys.argv[1], '*.zip')):
    base = os.path.basename(z)[:-4]
    sys.path.insert(0, os.path.join(z, base.replace('-internal-only-', '-')) if base.startswith('cassandra-driver') else z)
from cassandra.cluster import Cluster
c = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30); s = c.connect(); s.default_timeout = 120
t0 = time.time()
for i in range(40):
    s.execute("CREATE KEYSPACE IF NOT EXISTS lvks%d WITH replication = {'class':'SimpleStrategy','replication_factor':1}" % i)
    for j in range(25):
        s.execute("CREATE TABLE IF NOT EXISTS lvks%d.t%d (pk int PRIMARY KEY, v text)" % (i, j))
print("SEEDED 40 keyspaces x 25 tables in %.0f s" % (time.time() - t0), flush=True)
c.shutdown()
