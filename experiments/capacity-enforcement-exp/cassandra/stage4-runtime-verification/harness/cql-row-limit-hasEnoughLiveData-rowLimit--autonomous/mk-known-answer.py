#!/usr/bin/env python3
"""Synthetic unit.txt for the analyzer instrument check. Usage: mk-known-answer.py good|bad > unit.txt. 'bad': weightedSize grows with L in R=100."""
import sys
mode = sys.argv[1]; ROWS = 1000; LS = ['1', '50', '100', '101', '1000', '1000000', 'none']
o = ['ROWS=1000', 'firsttrigger=OK']
def lv(l): return 10**9 if l == 'none' else int(l)
for r, c, w in (('100', 100, 11047), ('ALL', 1000, 110811), ('500', 500, 55047)):
    p = 'R' + r
    o += [p + '.pre.size=0', p + '.entry.cachedLiveRows=%d' % c, p + '.base.weighted=%d' % w, p + '.base.size=1', p + '.base.heap=50000000']
    for rd in (1, 2, 3):
        for i, l in enumerate(LS):
            k = '%s.r%d.L%s' % (p, rd, l); dr = l != 'none' and c >= lv(l); hit = 1 if (r == 'ALL' or dr) else 0
            ww = w + (lv(l) if mode == 'bad' and r == '100' and l != 'none' else 0)
            o += [k + '.direct=' + str(dr).lower(), k + '.hit=%d' % hit, k + '.oor=%d' % (1 - hit), k + '.miss=0', k + '.weighted=%d' % ww, k + '.size=1', k + '.rows=%d' % min(ROWS, lv(l)), k + '.heap=50000000']
o += ['NEG.isRowCacheEnabled=false', 'NEG.hit=0', 'NEG.miss=0', 'NEG.oor=0', 'NEG.entry=absent', 'done=1']
print('\n'.join(o))
