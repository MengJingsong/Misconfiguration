#!/usr/bin/env python3
"""Amendment N6: 3 partitions of ~40 MiB (10,000 clustering rows x 4 KiB) into ks.big, protocol 4, UNLOGGED batches of 10 rows (20 rows = 80 KiB would exceed batch_size_fail_threshold 50 KiB).
Run with PYTHONPATH=<tree>/lib/cassandra-driver-internal-only-*.zip (cluster-run.py does this)."""
import os, random
from cassandra.cluster import Cluster
from cassandra.query import BatchStatement, BatchType
cl = Cluster(['127.0.0.1'], protocol_version=4, connect_timeout=30)
s = cl.connect('ks')
ins = s.prepare('INSERT INTO big (pk, ck, val) VALUES (?, ?, ?)')
rnd = random.Random(20261024)
total = 0
for pk in ('p1', 'p2', 'p3'):
    for start in range(0, 10000, 10):
        b = BatchStatement(batch_type=BatchType.UNLOGGED)
        for ck in range(start, start + 10):
            v = bytes(rnd.getrandbits(8) for _ in range(4096)) if False else os.urandom(4096)
            b.add(ins, (pk, ck, v)); total += 4096
        s.execute(b, timeout=60)
    print('partition', pk, 'done', total, flush=True)
print('payload bytes', total)
cl.shutdown()
