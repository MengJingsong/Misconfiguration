#!/usr/bin/env python3
"""Cluster-tier writer (B3c). usage: workload.py <lib-dir> tables <T> | blob
tables T: keyspace ks (RF 1), tables ks.t0..t(T-1) (pk int, ck int, v blob, PRIMARY KEY (pk, ck)); per table 1200 rows,
          1000 random bytes each, one partition (pk = 1).
blob:     table ks.big, one row with a 4 MiB random blob.
Uses the cassandra-driver zip bundled in the run copy's lib/ (the one cqlsh uses)."""
import glob, os, sys, time
lib = sys.argv[1]
for z in glob.glob(os.path.join(lib, '*.zip')):          # as bin/cqlsh.py does: the driver zip holds cassandra-driver-<ver>/
    base = os.path.basename(z)[:-4]
    sys.path.insert(0, os.path.join(z, base.replace('-internal-only-', '-')) if base.startswith('cassandra-driver') else z)
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args

c = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30)
s = c.connect()
s.default_timeout = 60
mode = sys.argv[2]
if mode == 'tables':
    T = int(sys.argv[3])
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    for i in range(T):
        s.execute("CREATE TABLE IF NOT EXISTS ks.t%d (pk int, ck int, v blob, PRIMARY KEY (pk, ck))" % i)
    print("EXPECTED created %d tables" % T, flush=True)
    t0 = time.time(); errs = 0; n = 0
    for i in range(T):
        ins = s.prepare("INSERT INTO ks.t%d (pk, ck, v) VALUES (?, ?, ?)" % i)
        args = [(1, k, os.urandom(1000)) for k in range(1200)]
        for ok, r in execute_concurrent_with_args(s, ins, args, concurrency=16, raise_on_first_error=False):
            n += 1
            if not ok: errs += 1
    print("WORKLOAD tables=%d rows=%d errors=%d seconds=%.1f" % (T, n, errs, time.time() - t0), flush=True)
elif mode == 'blob':
    s.execute("CREATE KEYSPACE IF NOT EXISTS ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
    s.execute("CREATE TABLE IF NOT EXISTS ks.big (pk int PRIMARY KEY, v blob)")
    ins = s.prepare("INSERT INTO ks.big (pk, v) VALUES (?, ?)")
    s.execute(ins, (1, os.urandom(4 * 1024 * 1024)))
    print("WORKLOAD blob 4194304 bytes written", flush=True)
c.shutdown()
