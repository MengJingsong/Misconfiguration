#!/usr/bin/env python3
"""Row-cache workload client. Usage: loader.py <driver-dir> <host> <port> <mode> <args...>
  load  <table> <first_pk> <count>   INSERT ck 0..299 with a 1024 B blob per row (bytes seeded by pk), 128 requests in flight
  del   <table> <first_pk> <count>   DELETE ck 0..199 of each partition, one statement per row (row deletions)
  full  <table> <first_pk> <count>   SELECT * FROM <table> WHERE pk=<pk> (whole partitions; warm-up of the read path on the table that is not under test)
  scan  <table> <first_pk> <count>   SELECT * FROM <table> WHERE pk=<pk> LIMIT 5 (simple statement) for pk in [first, first+count) in order; prints rows and bytes of 'v'
Prints one CLIENT_DONE line; exit 1 on any error."""
import sys, random, threading, time
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
host, port, mode, table, first, n = sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
c = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect('ks')
sem = threading.Semaphore(128); st = {'err': 0, 'rows': 0, 'ok': 0, 'bytes': 0}; lk = threading.Lock()
def done(res):
    rows = list(res) if res is not None else []
    with lk: st['rows'] += len(rows); st['ok'] += 1; st['bytes'] += sum(len(r.v) for r in rows if getattr(r, 'v', None) is not None)
    sem.release()
def done_w(_):
    with lk: st['ok'] += 1
    sem.release()
def bad(e):
    with lk: st['err'] += 1
    print('ERR', e); sem.release()
def go(ps, args, cb):
    sem.acquire(); f = s.execute_async(ps, args, timeout=120); f.add_callbacks(cb, bad)
t0 = time.time()
if mode == 'load':
    ps = s.prepare('INSERT INTO %s (pk, ck, v) VALUES (?,?,?)' % table)
    for pk in range(first, first + n):
        r = random.Random(pk)
        for ck in range(300): go(ps, (pk, ck, r.randbytes(1024)), done_w)
elif mode == 'del':
    ps = s.prepare('DELETE FROM %s WHERE pk=? AND ck=?' % table)
    for pk in range(first, first + n):
        for ck in range(200): go(ps, (pk, ck), done_w)
elif mode == 'scan':
    # simple (unprepared) statements on purpose: a prepared SELECT keeps the table's caching options from the time it was prepared (seen in the
    # shakedown, 2026-10-26: after ALTER TABLE the entries kept the old rows_per_partition), so every read is parsed against the current schema
    for pk in range(first, first + n): go('SELECT * FROM %s WHERE pk=%d LIMIT 5' % (table, pk), None, done)
elif mode == 'full':   # warm-up of the read path on a table whose row cache is off: whole partitions, rows discarded
    for pk in range(first, first + n): go('SELECT * FROM %s WHERE pk=%d' % (table, pk), None, done)
for _ in range(128): sem.acquire()
print('CLIENT_DONE', mode, table, 'ok', st['ok'], 'rows', st['rows'], 'vbytes', st['bytes'], 'errors', st['err'], 'secs %.1f' % (time.time() - t0))
c.shutdown(); sys.exit(1 if st['err'] else 0)
