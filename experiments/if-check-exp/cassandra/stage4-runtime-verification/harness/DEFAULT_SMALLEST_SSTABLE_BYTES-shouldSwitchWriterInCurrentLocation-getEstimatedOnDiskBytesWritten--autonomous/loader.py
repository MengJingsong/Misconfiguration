#!/usr/bin/env python3
"""Deterministic loader (B3i.2 / B3i.3). Usage:
  loader.py <driver-dir> part  <table> <first_pk> <count>   rows_per_pk=10 (ks.<table>(pk bigint, ck int, v blob)), 1024-byte blobs seeded by (pk, ck)
  loader.py <driver-dir> flat  <table> <first_id> <count>   one row per id (ks.<table>(id bigint, v blob)), 1024-byte blobs seeded by id
  loader.py <driver-dir> wide  <table> <pk> <rows>          one partition of <rows> rows x 1 MiB (ks.<table>(pk bigint, ck int, v blob))
  loader.py <driver-dir> count <table> <kind>               paged read-back of the row count (kind part|flat)
  loader.py <driver-dir> spot  <table> <first_pk> <count>   spot check: 40 evenly spaced pks in [first, first+count) must hold 10 rows whose blobs equal the seeded bytes
  host from $STAGE4_HOST (default 127.0.0.1)"""
import sys, random, threading, os
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
mode, table = sys.argv[2], sys.argv[3]
c = Cluster([os.environ.get('STAGE4_HOST', '127.0.0.1')], protocol_version=5, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect('ks')
sem = threading.Semaphore(128); err = [0]
def ok(_): sem.release()
def bad(e): err[0] += 1; print('ERR', e); sem.release()
def go(ps, args):
    sem.acquire(); f = s.execute_async(ps, args); f.add_callbacks(ok, bad)
if mode == 'part':
    first, n = int(sys.argv[4]), int(sys.argv[5]); ps = s.prepare(f'INSERT INTO {table} (pk, ck, v) VALUES (?,?,?)')
    for pk in range(first, first + n):
        r = random.Random(pk)
        for ck in range(10): go(ps, (pk, ck, r.randbytes(1024)))
elif mode == 'flat':
    first, n = int(sys.argv[4]), int(sys.argv[5]); ps = s.prepare(f'INSERT INTO {table} (id, v) VALUES (?,?)')
    for i in range(first, first + n): go(ps, (i, random.Random(i).randbytes(1024)))
elif mode == 'wide':
    pk, rows = int(sys.argv[4]), int(sys.argv[5]); ps = s.prepare(f'INSERT INTO {table} (pk, ck, v) VALUES (?,?,?)')
    r = random.Random(0xBEEF)
    for ck in range(rows): go(ps, (pk, ck, r.randbytes(1024 * 1024)))
elif mode == 'spot':
    first, n = int(sys.argv[4]), int(sys.argv[5]); bad_ = 0; chk = 0
    ps = s.prepare(f'SELECT ck, v FROM {table} WHERE pk = ?')
    for pk in [first + (i * (n - 1)) // 39 for i in range(40)]:
        r = random.Random(pk); exp = [r.randbytes(1024) for _ in range(10)]
        rows = sorted(s.execute(ps, (pk,), timeout=60), key=lambda x: x.ck)
        chk += 1
        if len(rows) != 10 or any(bytes(x.v) != e for x, e in zip(rows, exp)): bad_ += 1; print('BAD pk', pk, len(rows))
    print('SPOT checked', chk, 'bad', bad_); c.shutdown(); sys.exit(1 if bad_ else 0)
elif mode == 'count':
    from cassandra.query import SimpleStatement
    q = 'SELECT pk FROM ' + table if sys.argv[4] == 'part' else 'SELECT id FROM ' + table
    n = sum(1 for _ in s.execute(SimpleStatement(q, fetch_size=10000), timeout=600))
    print('COUNT', n); c.shutdown(); sys.exit(0)
for _ in range(128): sem.acquire()
print('LOADER_DONE', mode, table, 'errors', err[0])
c.shutdown(); sys.exit(1 if err[0] else 0)
