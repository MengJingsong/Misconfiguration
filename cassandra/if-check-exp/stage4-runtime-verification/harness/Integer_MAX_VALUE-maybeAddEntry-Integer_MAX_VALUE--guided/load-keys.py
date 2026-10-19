#!/usr/bin/env python3
"""usage: load-keys.py <keyspace.table> <N> <K> <seed>   (Integer_MAX_VALUE case 9c)
Inserts N rows (k = key i of K bytes, v = i) with a prepared INSERT, 32 in flight, in chunks of 1,000. Prints one summary line."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imvdrv

tbl, N, K, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
cl, ses = imvdrv.driver()
from cassandra.concurrent import execute_concurrent_with_args
ps = ses.prepare(f'INSERT INTO {tbl} (k, v) VALUES (?, ?)')
t0 = time.time()
for a in range(0, N, 1000):
    args = [(imvdrv.key(seed, i, K), i) for i in range(a, min(N, a + 1000))]
    execute_concurrent_with_args(ses, ps, args, concurrency=32, raise_on_first_error=True)
print(f'LOAD {tbl}: {N} rows of {K}-byte keys, seed {seed}, in {time.time() - t0:.1f} s')
cl.shutdown()
