#!/usr/bin/env python3
"""usage: send-cql.py probe | build | big-insert <N>      (networking_cache_size case 9c)
probe       protocol 5: SELECT release_version FROM system.local
build       protocol 4: keyspace ks1 (RF 1), table ks1.t (pk int PRIMARY KEY, v blob), rows pk 0-7 with 1,048,576 random bytes (seed 7)
big-insert  protocol 5: prepared INSERT INTO ks1.t (pk, v) VALUES (?, ?), pk 1000 + i, 1,000,000 random bytes, one at a time;
            then cluster.shutdown(). Prints the number acknowledged."""
import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drv
drv.load()
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra import ConsistencyLevel

cmd = sys.argv[1]
proto = 4 if cmd == 'build' else 5
cl = Cluster(['127.0.0.1'], protocol_version=proto, execution_profiles={EXEC_PROFILE_DEFAULT: ExecutionProfile(request_timeout=60, consistency_level=ConsistencyLevel.ONE)})
ses = cl.connect()
if cmd == 'probe':
    print('probe', ses.execute('SELECT release_version FROM system.local').one()[0])
elif cmd == 'build':
    ses.execute("CREATE KEYSPACE IF NOT EXISTS ks1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    ses.execute('CREATE TABLE IF NOT EXISTS ks1.t (pk int PRIMARY KEY, v blob)')
    rnd = random.Random(7)
    ps = ses.prepare('INSERT INTO ks1.t (pk, v) VALUES (?, ?)')
    for pk in range(8):
        ses.execute(ps, (pk, rnd.randbytes(1048576)))
    print('built', len(list(ses.execute('SELECT pk FROM ks1.t'))), 'rows')
elif cmd == 'big-insert':
    n = int(sys.argv[2])
    rnd = random.Random(1000)
    ps = ses.prepare('INSERT INTO ks1.t (pk, v) VALUES (?, ?)')
    ok = 0
    for i in range(n):
        ses.execute(ps, (1000 + i, rnd.randbytes(1000000)))
        ok += 1
    print('big-insert acknowledged', ok, 'of', n)
cl.shutdown()
