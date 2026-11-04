#!/usr/bin/env python3
"""Instrument check for analyze_unit.py: writes a synthetic unit.txt from the predicted formulas (good), or with shape B pulling less at gppl=1 (bad: a cap that binds).
Usage: mk-known-answer.py good|bad <out>. good must give CLASS row 1; bad must flag B_pull and B_alloc."""
import sys
mode, out = sys.argv[1], sys.argv[2]; NO = 'NO_LIMIT'; B = 100000; BT = 4 * B
L = ['A_PARTS=20', 'A_ROWS=1000', 'B_PARTS=4', 'B_ROWS=%d' % B, 'reps=3', 'maxMemory=1', 'firsttrigger=OK returned=200 pulled=220']
gs = [1, 10, NO]; rls = [100, 10000, NO]; num = lambda x: 2**31 - 1 if x == NO else x
for rep in range(3):
    for rl in rls:
        for g in gs:
            G = 20 * min(num(g), 1000); r = num(rl)
            ret = min(G, r)
            pl = ret if G > r else (20 * (num(g) + 1) if g != NO else 20000)
            L.append('run shape=A gppl=%s rowLimit=%s returned=%d pulled=%d parts=20 counted=%d cip_before_close=0 cip=0 rowsCounted=%d alloc=%d' % (g, rl, ret, pl, ret, ret, 300 * pl + 5000))
            if mode == 'bad' and g == 1: pb = 20
            else: pb = BT if rl == NO else rl
            L.append('run shape=B gppl=%s rowLimit=%s returned=%d pulled=%d parts=4 counted=%d cip_before_close=0 cip=%d rowsCounted=%d alloc=%d' % (g, rl, pb, pb, 4 if rl == NO else 0, 1 if rl == NO else 0, pb, 300 * pb + 5000))
L.append('done=1'); open(out, 'w').write('\n'.join(L) + '\n')
