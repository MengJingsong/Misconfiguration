#!/usr/bin/env python3
"""Cluster-tier driver (B3c). usage: workload.py <lib dir> ddl '<cql>' | load <keyfile> <offset> <count> <value bytes>
load: INSERT INTO ks.t (k, v) for keys offset..offset+count-1 of the key file (hex), v = random bytes; CL ONE; errors counted."""
import glob, os, sys, time, binascii
lib = sys.argv[1]
for z in glob.glob(os.path.join(lib, '*.zip')):
    base = os.path.basename(z)[:-4]
    sys.path.insert(0, os.path.join(z, base.replace('-internal-only-', '-')) if base.startswith('cassandra-driver') else z)
from cassandra.cluster import Cluster
from cassandra.concurrent import execute_concurrent_with_args
c = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30); s = c.connect(); s.default_timeout = 120
if sys.argv[2] == 'ddl':
    s.execute(sys.argv[3]); print("DDL ok", flush=True)
else:
    keyfile, off, cnt, vb = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
    keys = [binascii.unhexlify(l.strip()) for l in open(keyfile)][off:off + cnt]
    ins = s.prepare("INSERT INTO ks.t (k, v) VALUES (?, ?)")
    t0 = time.time(); err = n = 0
    for ok, r in execute_concurrent_with_args(s, ins, [(k, os.urandom(vb)) for k in keys], concurrency=32, raise_on_first_error=False):
        n += 1; err += (not ok)
    print("WORKLOAD rows=%d errors=%d bytes=%d seconds=%.1f" % (n, err, n * vb, time.time() - t0), flush=True)
c.shutdown()
