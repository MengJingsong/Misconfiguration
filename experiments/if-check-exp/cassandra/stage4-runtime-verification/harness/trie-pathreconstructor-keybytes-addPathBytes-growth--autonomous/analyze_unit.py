#!/usr/bin/env python3
"""Unit-tier analysis against B2f / B2g. Usage: analyze_unit.py <results.csv>"""
import sys, collections
rows = []
for l in open(sys.argv[1]):
    f = l.strip().split(',')
    d = dict(group=f[0], buf=f[1]); d.update({kv.split('=')[0]: int(kv.split('=')[1]) for kv in f[2:]})
    rows.append(d)
cell = collections.defaultdict(list)
for r in rows: cell[(r['group'], r['buf'], r['L'], r['N'])].append(r)
print('%-7s %-8s %7s %7s  %-14s %-12s %12s %12s %10s' % ('group', 'buf', 'L', 'N', 'capacity(3x)', 'range', 'sizeOnHeap', 'sizeOffHeap', 'iterAlloc'))
res = {}
for k in sorted(cell):
    g, b, L, N = k; rs = cell[k]; caps = [r['capacity'] for r in rs]
    res[k] = caps
    print('%-7s %-8s %7d %7d  %-14s %-12s %12d %12d %10d' % (g, b, L, N, '/'.join(map(str, caps)), '[%d,%d]' % (L, 2 * L + 16), rs[0]['sizeOnHeap'], rs[0]['sizeOffHeap'], rs[0]['iterAllocBytes']))
ok = True
def chk(c, m):
    global ok
    print(('OK   ' if c else 'FAIL ') + m); ok = ok and c
chk(all(len(rs) == 3 for rs in cell.values()), 'every cell ran 3 times')
chk(all(len(set(c)) == 1 for c in res.values()), 'repeats identical within each cell')
chk(all(r['entries'] == r['N'] for r in rows), 'entries walked == N in every row')
for (g, b, L, N), caps in sorted(res.items()):
    if g in ('lsweep', 'nsweep') and N >= 1:
        chk(L <= caps[0] <= 2 * L + 16 or (L < 32 and caps[0] == 32), 'capacity %d within [L=%d, 2L+16=%d] (%s N=%d)' % (caps[0], L, 2 * L + 16, b, N))
chk(all(caps[0] == 32 for (g, b, L, N), caps in res.items() if g == 'empty'), 'empty trie capacity 32')
for L in (16, 1000):
    for b in ('ON_HEAP', 'OFF_HEAP'):
        v = {res[('nsweep', b, L, N)][0] for N in (1, 1000, 100000)}
        chk(len(v) == 1, 'N-independence at L=%d %s: capacities %s' % (L, b, sorted(v)))
for g, L, N in [('lsweep', l, 1000) for l in (16, 1000, 20000, 65535, 131070)]:
    chk(res[(g, 'ON_HEAP', L, N)] == res[(g, 'OFF_HEAP', L, N)], 'buffer-type independence at L=%d N=%d: %s vs %s' % (L, N, res[(g, 'ON_HEAP', L, N)], res[(g, 'OFF_HEAP', L, N)]))
for L in (16, 1000):
    on = [cell[('nsweep', 'ON_HEAP', L, N)][0]['sizeOnHeap'] for N in (1, 1000, 100000)]
    off = [cell[('nsweep', 'OFF_HEAP', L, N)][0]['sizeOffHeap'] for N in (1, 1000, 100000)]
    chk(on[0] < on[1] < on[2] or off[0] < off[1] < off[2], 'control moves: L=%d sizeOnHeap(ON_HEAP) %s ; sizeOffHeap(OFF_HEAP) %s' % (L, on, off))
big = [res[('lsweep', 'ON_HEAP', L, 1000)][0] for L in (16, 1000, 20000, 65535, 131070)]
chk(big[0] == 32 and all(c > 32 for c in big[1:]) and big == sorted(big), 'instrument sensitive to L: %s' % big)
print('ALL OK' if ok else 'SOME FAILED')
