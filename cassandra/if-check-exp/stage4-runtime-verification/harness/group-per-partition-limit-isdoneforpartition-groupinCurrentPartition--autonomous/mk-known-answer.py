#!/usr/bin/env python3
"""Instrument check for analyze_unit.py: writes a synthetic unit.txt. good: the analyzer must print CLASS row 1. bad: retained heap grows with N (a cap that binds), must NOT match row 1."""
import sys
mode, out = sys.argv[1], sys.argv[2]; R = 100000
L = ['R=%d' % R, 'reps=3', 'firsttrigger=OK groups=10 pulled=11']
for i in range(3): L.append('noise rep=%d used_before=50000000 used_after=50000%03d' % (i, i * 7))
ns = [1, 10, 100, 1000, 'NO_LIMIT']
for ctl in (0, 1):
    for n in ns:
        nn = R if n == 'NO_LIMIT' else n
        for rep in range(3):
            base = 50000000 + (nn * 150 if (ctl or mode == 'bad') else 0) + rep * 1000
            L.append('%s N=%s groups=%d pulled=%d counted=%d countedInPartition=%d rowsCounted=%d alloc=%d used_before=50000000 used_after=%d kept=%d' %
                     ('ctl' if ctl else 'run', n, nn, nn + (1 if nn < R else 0), nn, nn, nn, 400 * nn + 20000, base, nn if ctl else 0))
L.append('done=1'); open(out, 'w').write('\n'.join(L) + '\n')
