#!/usr/bin/env python3
"""usage: read-keys.py <keyspace.table> <N> <K> <seed> <nstar> <trace file>   (Integer_MAX_VALUE case 9c, amended 2026-10-15)
Reads every row's token(k) and v in token order (one paged scan) to get each key's rank, then point-reads 5 ranks below n*
(0, n*/4, n*/2, 3n*/4, n*-1, clipped to the table) and the 5 highest ranks, regenerating each key from its seed. For each point
read prints one JSON line: rank, index (v), found, v read back, and the 'scan' trace lines that read produced for this table."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imvdrv

tbl, N, K, seed, nstar, trace = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
ks, t = tbl.split('.')
cl, ses = imvdrv.driver()
from cassandra.query import SimpleStatement
order = [r.v for r in ses.execute(SimpleStatement(f'SELECT token(k), v FROM {tbl}', fetch_size=500))]
print(json.dumps({'scan_rows': len(order), 'N': N, 'distinct': len(set(order))}))
top = min(N, nstar)
ranks = sorted({r for r in (0, top // 4, top // 2, 3 * top // 4, top - 1) if 0 <= r < len(order)} | {r for r in range(len(order) - 5, len(order)) if r >= 0})
ps = ses.prepare(f'SELECT v FROM {tbl} WHERE k = ?')


def size(p):
    try:
        return os.path.getsize(p)
    except FileNotFoundError:
        return 0


for r in ranks:
    idx = order[r]
    off = size(trace)
    row = ses.execute(ps, (imvdrv.key(seed, idx, K),)).one()
    time.sleep(0.2)
    with open(trace) as f:
        f.seek(off)
        lines = [l.strip() for l in f.read().splitlines() if l.startswith('scan ') and f'/{ks}/{t}-' in l]
    print(json.dumps({'rank': r, 'index': idx, 'found': row is not None, 'v': row.v if row else None,
                      'predicted_skips': 0 if r < nstar else r - nstar + 1, 'scan': lines}))
cl.shutdown()
