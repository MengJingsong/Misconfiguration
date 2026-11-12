import os, sys
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
mode, n, size, conc = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
s = Cluster(['127.0.0.1'], port=9342).connect()
s.default_timeout = 60
if mode == 'write':
    s.execute("CREATE KEYSPACE IF NOT EXISTS o43 WITH replication={'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS o43.t (k int PRIMARY KEY, v blob) WITH caching={'keys':'ALL','rows_per_partition':'ALL'}")
    ins = s.prepare("INSERT INTO o43.t (k, v) VALUES (?, ?)")
    for k in range(n): s.execute(ins, (k, os.urandom(size)))
else:
    sel = s.prepare("SELECT k, v FROM o43.t WHERE k = ?")
    res = execute_concurrent_with_args(s, sel, [(k,) for k in range(n)], concurrency=conc)
    print("ok", sum(1 for ok, _ in res if ok))
