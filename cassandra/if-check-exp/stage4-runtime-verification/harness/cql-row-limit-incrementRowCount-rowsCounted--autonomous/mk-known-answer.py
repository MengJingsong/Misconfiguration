#!/usr/bin/env python3
"""Synthetic unit.txt for the analyzer instrument check. Usage: mk-known-answer.py good|bad [source] > unit.txt. 'bad': retained heap independent of width (a shared buffer)."""
import sys
mode = sys.argv[1]; SRC = int(sys.argv[2]) if len(sys.argv) > 2 else 1200000; REPS = 5
o = ['SOURCE=%d' % SRC, 'REPS=%d' % REPS, 'warm.rowsCounted=100', 'warm.isDone=true', 'warm.out=100', 'warm.outLive=100', 'warm.pulled=100', 'firsttrigger=OK']
grid = {16: [1, 100, 1000, 10000, 1000000], 1024: [1, 100, 1000, 10000], 65536: [1, 100, 1000]}
def row(w): return 250 + (16 if mode == 'bad' else w)
for r in range(1, REPS + 1):
    for w, Ls in grid.items():
        for L in Ls:
            k = 'P.w%d.L%d.r%d' % (w, L, r)
            o += ['%s.rowsCounted=%d' % (k, L), '%s.isDone=true' % k, '%s.out=%d' % (k, L), '%s.outLive=%d' % (k, L), '%s.pulled=%d' % (k, L), '%s.retained=%d' % (k, L * row(w) + 1000 * r), '%s.unshared=%d' % (k, L * row(w))]
    k = 'NONE.w16.r%d' % r; o += ['%s.rowsCounted=-1' % k, '%s.isDone=na' % k, '%s.out=%d' % (k, SRC), '%s.outLive=%d' % (k, SRC), '%s.pulled=%d' % (k, SRC), '%s.retained=%d' % (k, SRC * 266), '%s.unshared=%d' % (k, SRC * 266)]
    for L in (1, 100, 1000):
        k = 'DEAD.w16.L%d.r%d' % (L, r); o += ['%s.rowsCounted=%d' % (k, L), '%s.isDone=true' % k, '%s.out=%d' % (k, 10 * L - 9), '%s.outLive=%d' % (k, L), '%s.pulled=%d' % (k, 10 * L - 9)]
    for w in (16, 1024, 65536):
        rs = row(w); rows = (8 << 20) // rs + 1; k = 'CTL.w%d.r%d' % (w, r)
        o += ['%s.rows=%d' % (k, rows), '%s.unshared=%d' % (k, rows * rs), '%s.retained=%d' % (k, rows * rs + 5000), '%s.pulled=%d' % (k, rows)]
o.append('done=1'); print('\n'.join(o))
