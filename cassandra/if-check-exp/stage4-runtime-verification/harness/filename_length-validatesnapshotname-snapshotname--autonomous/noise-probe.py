#!/usr/bin/env python3
"""Supplementary heap-noise probe (added after run 1's one 'NO': N=2M heap delta L=255 vs L=100 = 1.49 MiB > 1 MiB tolerance).
Reuses cluster-run.py's functions on the run-1 data directory (2M rows kept): validation true, alternating L=100/255 three times each.
Output: <run>/cluster/noise-summary.txt. Not a second run: it only characterises the run-1 heap-delta noise."""
import sys, re
src = open(__import__('os').path.dirname(__import__('os').path.abspath(__file__)) + '/cluster-run.py').read()
src = re.sub(r'\nmain\(\)\s*$', '\n', src)
sys.argv = ['x', sys.argv[1] if len(sys.argv) > 1 else 'run1']
g = {'__name__': 'cp'}; exec(compile(src, 'cluster-run.py', 'exec'), g)
SUM2 = open(g['LOG'] + '/noise-summary.txt', 'a'); g['SUM'] = SUM2
g['start'](True)
try:
    g['nt']('disableautocompaction keyspace1')
    g['snapshot'](2000000, 'noise-warm', 100, True, True)
    res = []
    for i in range(3):
        for L in (100, 255):
            r = g['snapshot'](2000000, f'noise{i}', L, True, True); res.append((L, r['heap'], r['rss'], r['phys']))
    for L, h, rs, p in res: g['note'](f'NOISE L={L} heapDelta={h} rssDelta={rs} physDelta={p}')
    h100 = [h for L, h, _, _ in res if L == 100]; h255 = [h for L, h, _, _ in res if L == 255]
    g['note'](f'NOISE heapDelta L=100: {h100} L=255: {h255}; range across all six = {max(h100+h255)-min(h100+h255)} B')
finally:
    g['stop']()
g['note']('noise-probe done')
