#!/usr/bin/env python3
"""Workload client. Usage: query.py <driver-dir> <host> <port> <mode> <args...>
  load  <first_k> <count> <rows>      INSERT ck 0..rows-1, 100-byte blob 'v', for k in [first_k, first_k+count) (128 in flight)
  group <fetch_size> <N|absent> <reps> <markerfile> <label>
        for rep in 1..reps: for k in 0..9: SELECT k, ck, count(*) FROM ks.t WHERE k=<k> GROUP BY k, ck [PER PARTITION LIMIT N] with fetch_size,
        every page read; writes a marker line 'epoch_ms label rep k rows' after each query (rows = rows returned over all pages) and checks rows == min(N, ROWS).
  point <reps> <markerfile> <label>   SELECT * FROM ks.t WHERE k=<k> AND ck=5 for k in 0..9, reps times (unrelated query: the heap noise reference)
Prints CLIENT_DONE; exit 1 on a wrong row count or any error."""
import sys, time, os
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra.query import SimpleStatement
host, port, mode = sys.argv[2], int(sys.argv[3]), sys.argv[4]
c = Cluster([host], port=port, protocol_version=4, load_balancing_policy=DCAwareRoundRobinPolicy(local_dc='datacenter1'), token_metadata_enabled=False)
s = c.connect('ks'); ROWS = int(os.environ.get('STAGE4_ROWS_PER_PK', 200000))
if mode == 'load':
    import threading
    first, n, rows = int(sys.argv[5]), int(sys.argv[6]), int(sys.argv[7])
    sem = threading.Semaphore(128); err = [0]
    def bad(e): err[0] += 1; print('ERR', e); sem.release()
    ps = s.prepare('INSERT INTO t (k, ck, v) VALUES (?,?,?)'); v = b'x' * 100; t0 = time.time()
    for k in range(first, first + n):
        for ck in range(rows):
            sem.acquire(); f = s.execute_async(ps, (k, ck, v), timeout=120); f.add_callbacks(lambda r: sem.release(), bad)
    for _ in range(128): sem.acquire()
    print('CLIENT_DONE load errors', err[0], 'secs %.1f' % (time.time() - t0)); c.shutdown(); sys.exit(1 if err[0] else 0)
if mode == 'group':
    fs, N, reps, marker, label = int(sys.argv[5]), sys.argv[6], int(sys.argv[7]), sys.argv[8], sys.argv[9]
    want = ROWS if N == 'absent' else min(int(N), ROWS); bad = 0
    with open(marker, 'a') as mf:
        for rep in range(1, reps + 1):
            for k in range(10):
                q = 'SELECT k, ck, count(*) FROM t WHERE k=%d GROUP BY k, ck%s' % (k, '' if N == 'absent' else ' PER PARTITION LIMIT %s' % N)
                rows = 0; t0 = time.time()
                for _ in s.execute(SimpleStatement(q, fetch_size=fs), timeout=600): rows += 1   # iterating pulls every page
                mf.write('%d %s %d %d %d %.3f\n' % (int(time.time() * 1000), label, rep, k, rows, time.time() - t0)); mf.flush()
                if rows != want: bad += 1; print('ROWS MISMATCH', label, rep, k, rows, want)
    print('CLIENT_DONE group', label, 'wrong_row_counts', bad); c.shutdown(); sys.exit(1 if bad else 0)
if mode == 'point':
    reps, marker, label = int(sys.argv[5]), sys.argv[6], sys.argv[7]
    with open(marker, 'a') as mf:
        for rep in range(1, reps + 1):
            for k in range(10):
                t0 = time.time(); r = list(s.execute('SELECT * FROM t WHERE k=%d AND ck=5' % k, timeout=60))
                mf.write('%d %s %d %d %d %.3f\n' % (int(time.time() * 1000), label, rep, k, len(r), time.time() - t0))
    print('CLIENT_DONE point'); c.shutdown(); sys.exit(0)
