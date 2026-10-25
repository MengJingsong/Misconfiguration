#!/usr/bin/env python3
"""Row-cache workload client (B3i.1-2). Usage: loader.py <driver-dir> <host> <port> <mode> <args...>
  load <first_pk> <count>             ks.t (pk int, ck int, v blob): 16 rows x 4096 B per partition, blobs seeded by pk
  scan <first_pk> <count>             SELECT * FROM ks.t WHERE pk=? over [first, first+count), 128 in flight; prints rows and bytes
  rand <seed> <seconds> <npk>         random pks in [0, npk) for <seconds>
  count                               (not used)
Prints one result line per run."""
import sys, random, threading, time
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
host, port, mode = sys.argv[2], int(sys.argv[3]), sys.argv[4]
c = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect('ks')
sem = threading.Semaphore(128); st = {'err': 0, 'rows': 0, 'ok': 0}; lk = threading.Lock()
def done(res):
    n = len(res) if res is not None else 0
    with lk: st['rows'] += n; st['ok'] += 1
    sem.release()
def done_w(_):
    with lk: st['ok'] += 1
    sem.release()
def bad(e):
    with lk: st['err'] += 1
    print('ERR', e); sem.release()
def go(ps, args, cb=done):
    sem.acquire(); f = s.execute_async(ps, args, timeout=120); f.add_callbacks(cb, bad)
t0 = time.time()
if mode == 'load':
    first, n = int(sys.argv[5]), int(sys.argv[6]); ps = s.prepare('INSERT INTO t (pk, ck, v) VALUES (?,?,?)')
    for pk in range(first, first + n):
        r = random.Random(pk)
        for ck in range(16): go(ps, (pk, ck, r.randbytes(4096)), done_w)
elif mode == 'scan':
    first, n = int(sys.argv[5]), int(sys.argv[6]); ps = s.prepare('SELECT * FROM t WHERE pk = ?')
    for pk in range(first, first + n): go(ps, (pk,))
elif mode == 'rand':
    seed, secs, npk = int(sys.argv[5]), float(sys.argv[6]), int(sys.argv[7]); ps = s.prepare('SELECT * FROM t WHERE pk = ?'); r = random.Random(seed)
    end = time.time() + secs
    while time.time() < end: go(ps, (r.randrange(npk),))
for _ in range(128): sem.acquire()
print('CLIENT_DONE', mode, 'ok', st['ok'], 'rows', st['rows'], 'errors', st['err'], 'secs %.1f' % (time.time() - t0))
c.shutdown(); sys.exit(1 if st['err'] else 0)
