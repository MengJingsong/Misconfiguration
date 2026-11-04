#!/usr/bin/env python3
"""Loader for the cluster tier of tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous (B3c as amended, 2026-10-26).
usage: load.py <host> <rows> <ttl> <name:pct> [<name:pct> ...]    (python3 -I load.py; the driver comes from $TD_DRIVER)
For each table ks.<name>: UPDATE ... USING TTL <ttl> SET v=? WHERE k=? for keys with (k mod 100) < pct, plain UPDATE for the rest, one
200-byte random value per key. Prints 'loaded <name> rows=<n> ttl_rows=<m> t_last_write=<epoch>' per table. Flushing is done by the caller.
Table name 'go' additionally gets nothing here; the overlap sstable is written by the caller with the 'extra' mode:
usage: load.py <host> extra <name> <count>    writes <count> non-TTL keys 1000000.. into ks.<name>."""
import os, sys, time, random
sys.path.insert(0, os.environ['TD_DRIVER'])
from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.concurrent import execute_concurrent, execute_concurrent_with_args

host = sys.argv[1]
cl = Cluster([host], port=9042, protocol_version=4, token_metadata_enabled=False,
             execution_profiles={EXEC_PROFILE_DEFAULT: ExecutionProfile(load_balancing_policy=DCAwareRoundRobinPolicy(), request_timeout=60)})
s = cl.connect('ks')
rnd = random.Random(1234)
blob = lambda: bytes(rnd.getrandbits(8) for _ in range(200))
vals = [blob() for _ in range(1000)]  # 1000 distinct random values reused: incompressible per value, cheap to generate
if sys.argv[2] == 'extra':
    name, count = sys.argv[3], int(sys.argv[4])
    st = s.prepare(f'UPDATE {name} SET v=? WHERE k=?')
    execute_concurrent_with_args(s, st, [(vals[i % 1000], 1000000 + i) for i in range(count)], concurrency=100, raise_on_first_error=True)
    print(f'extra {name} rows={count} t_last_write={int(time.time())}', flush=True)
else:
    rows, ttl = int(sys.argv[2]), int(sys.argv[3])
    for spec in sys.argv[4:]:
        name, pct = spec.split(':'); pct = int(pct)
        stt = s.prepare(f'UPDATE {name} USING TTL {ttl} SET v=? WHERE k=?')
        stp = s.prepare(f'UPDATE {name} SET v=? WHERE k=?')
        n_ttl = 0
        batch = []
        for k in range(rows):
            if k % 100 < pct:
                batch.append((stt, (vals[k % 1000], k))); n_ttl += 1
            else:
                batch.append((stp, (vals[k % 1000], k)))
            if len(batch) == 20000 or k == rows - 1:
                res = execute_concurrent(s, batch, concurrency=150, raise_on_first_error=True)
                batch = []
        print(f'loaded {name} rows={rows} ttl_rows={n_ttl} t_last_write={int(time.time())}', flush=True)
cl.shutdown()
