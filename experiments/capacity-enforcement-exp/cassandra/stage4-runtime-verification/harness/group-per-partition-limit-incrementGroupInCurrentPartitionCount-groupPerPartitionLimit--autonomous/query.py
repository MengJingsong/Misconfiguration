#!/usr/bin/env python3
"""Workload client. Usage: query.py <driver-dir> <host> <port> <mode> <args...>
  load  <first_pk> <count> <rows>       INSERT (pk, ck1=i//100, ck2=i%100, 100-byte blob) for i in 0..rows-1, for pk in [first_pk, first_pk+count) (128 in flight)
  scan  <A|B> <fetch_size> <L|abs> <reps> <markerfile> <label>
        A: SELECT pk, ck1, count(*) FROM t GROUP BY pk, ck1 [PER PARTITION LIMIT L]   (many small groups)
        B: SELECT pk, count(*) FROM t GROUP BY pk [PER PARTITION LIMIT L]             (one large group per partition)
        range query over the whole table, every page read; marker line 'epoch_ms label rep rows secs' after each query; rows must equal
        A: PARTS*min(L, ROWS/100), B: PARTS (PARTS = 20). Exit 1 on a wrong count.
  point <reps> <markerfile> <label>     SELECT * FROM t WHERE pk=<k> AND ck1=5 AND ck2=5 for k in 0..9 (unrelated query: the heap noise reference)
Prints CLIENT_DONE."""
import sys, time, os
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
host, port, mode = sys.argv[2], int(sys.argv[3]), sys.argv[4]
c = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect('ks'); ROWS = int(os.environ.get('STAGE4_ROWS_PER_PK', 200000)); PARTS = 20
if mode == 'load':
    import threading
    first, n, rows = int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
    sem = threading.Semaphore(128); err = [0]
    def bad(e): err[0] += 1; print('ERR', e); sem.release()
    ps = s.prepare('INSERT INTO t (pk, ck1, ck2, v) VALUES (?,?,?,?)'); v = b'x' * 100; t0 = time.time()
    for k in range(first, first + n):
        for i in range(rows):
            sem.acquire(); f = s.execute_async(ps, (k, i // 100, i % 100, v), timeout=120); f.add_callbacks(lambda r: sem.release(), bad)
    for _ in range(128): sem.acquire()
    print('CLIENT_DONE load errors', err[0], 'secs %.1f' % (time.time() - t0)); c.shutdown(); sys.exit(1 if err[0] else 0)
if mode == 'scan':
    shape, fs, L, reps, marker, label = sys.argv[5], int(sys.argv[6]), sys.argv[7], int(sys.argv[8]), sys.argv[9], sys.argv[10]
    groups_per_pk = ROWS // 100
    want = PARTS * (groups_per_pk if L == 'abs' else min(int(L), groups_per_pk)) if shape == 'A' else PARTS
    lim = '' if L == 'abs' else ' PER PARTITION LIMIT %s' % L
    q = ('SELECT pk, ck1, count(*) FROM t GROUP BY pk, ck1' if shape == 'A' else 'SELECT pk, count(*) FROM t GROUP BY pk') + lim
    bad = 0
    with open(marker, 'a') as mf:
        for rep in range(1, reps + 1):
            rows = 0; t0 = time.time()
            for _ in s.execute(SimpleStatement(q, fetch_size=fs), timeout=1800): rows += 1   # iterating pulls every page
            mf.write('%d %s %d %d %.3f\n' % (int(time.time() * 1000), label, rep, rows, time.time() - t0)); mf.flush()
            if rows != want: bad += 1; print('ROWS MISMATCH', label, rep, rows, want)
    print('CLIENT_DONE scan', label, q, 'wrong_row_counts', bad); c.shutdown(); sys.exit(1 if bad else 0)
if mode == 'point':
    reps, marker, label = int(sys.argv[5]), sys.argv[6], sys.argv[7]
    with open(marker, 'a') as mf:
        for rep in range(1, reps + 1):
            for k in range(10):
                t0 = time.time(); r = list(s.execute('SELECT * FROM t WHERE pk=%d AND ck1=5 AND ck2=5' % k, timeout=60))
                mf.write('%d %s %d %d %.3f\n' % (int(time.time() * 1000), label, rep, len(r), time.time() - t0))
    print('CLIENT_DONE point'); c.shutdown(); sys.exit(0)
