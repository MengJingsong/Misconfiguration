#!/usr/bin/env python3
"""Row-cache workload client (case cql-row-limit-hasEnoughLiveData-rowLimit). Usage: loader.py <driver-dir> <host> <port> <mode> <table> <first> <count> [extra...]
  load <table> <first_pk> <count> <nck> <blob>   INSERT ck 0..nck-1 with a <blob>-byte value (bytes seeded by pk), 128 requests in flight
  full <table> <first_pk> <count>                SELECT * FROM <table> WHERE pk=<pk> (whole partitions; warm-up of the read path on the table that is not under test)
  q    <table> <first_pk> <count> <L|none>       SELECT * ... WHERE pk=<pk> [LIMIT L] for pk in [first, first+count) in order (populate pass)
  rnd  <table> <seed> <count> <L|none> <npk>     the same query for <count> pk drawn uniformly from [0, npk) with random.Random(seed)
All SELECTs are simple (unprepared) statements with the driver's default page size (5000). Prints one CLIENT_DONE line (rows returned); exit 1 on any error."""
import sys, random, threading, time
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
host, port, mode, table, first, n = sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5], int(sys.argv[6]), int(sys.argv[7])
extra = sys.argv[8:]
c = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect('ks')
sem = threading.Semaphore(128); st = {'err': 0, 'rows': 0, 'ok': 0}; lk = threading.Lock()
def done(res):
    rows = list(res) if res is not None else []
    with lk: st['rows'] += len(rows); st['ok'] += 1
    sem.release()
def done_w(_):
    with lk: st['ok'] += 1
    sem.release()
def bad(e):
    with lk: st['err'] += 1
    print('ERR', e); sem.release()
def go(ps, args, cb):
    sem.acquire(); f = s.execute_async(ps, args, timeout=120); f.add_callbacks(cb, bad)
def sel(pk, L):
    return 'SELECT * FROM %s WHERE pk=%d%s' % (table, pk, '' if L == 'none' else ' LIMIT %s' % L)
t0 = time.time()
if mode == 'load':
    nck, blob = int(extra[0]), int(extra[1])
    ps = s.prepare('INSERT INTO %s (pk, ck, v) VALUES (?,?,?)' % table)
    for pk in range(first, first + n):
        r = random.Random(pk)
        for ck in range(nck): go(ps, (pk, ck, r.randbytes(blob)), done_w)
elif mode == 'full':
    for pk in range(first, first + n): go(sel(pk, 'none'), None, done)
elif mode == 'q':
    for pk in range(first, first + n): go(sel(pk, extra[0]), None, done)
elif mode == 'rnd':
    r = random.Random(first); L = extra[0]; npk = int(extra[1])
    for _ in range(n): go(sel(r.randrange(npk), L), None, done)
for _ in range(128): sem.acquire()
print('CLIENT_DONE', mode, table, 'ok', st['ok'], 'rows', st['rows'], 'errors', st['err'], 'secs %.1f' % (time.time() - t0))
c.shutdown(); sys.exit(1 if st['err'] else 0)
