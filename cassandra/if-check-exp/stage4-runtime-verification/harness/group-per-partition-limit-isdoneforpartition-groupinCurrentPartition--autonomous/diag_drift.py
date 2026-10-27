#!/usr/bin/env python3
"""POST-HOC diagnostic written after run 1's reading (not part of the frozen analysis, not used for the verdict row). Usage: diag_drift.py <arms-dir>
For selected arms: percentiles of (heap_used - first sample), the 20 s window trough (minimum used) relative to the first sample, and the maximum of the first 157 samples
(the sample count of the N=10000 arm). Shows whether the N=absent arm's higher peak is a per-query excursion or a slow rise of the post-collection floor."""
import sys, os
d = sys.argv[1]
S = [tuple(int(x) for x in l.split(',')) for l in open(os.path.join(d, 'samples.csv')) if l[:1].isdigit() and l.count(',') == 3]
ev = {}
for l in open(os.path.join(d, 'arms.txt')):
    p = l.split()
    if p[1] in ('START', 'END'): ev.setdefault(p[2], {})[p[1]] = int(p[0])
for a in ('f_N10000_P1000', 'f_Nabs_P1000', 'r_Nabs_P1000', 'c_Nabs_P300000'):
    w = [s for s in S if ev[a]['START'] <= s[0] <= ev[a]['END']]; b = w[0][1]
    x = sorted((s[1] - b) / 1e6 for s in w); n = len(x)
    print(a, 'samples', n, 'p50 %.1f p90 %.1f p99 %.1f max %.1f MB' % (x[n // 2], x[int(n * .9)], x[int(n * .99)], x[-1]), 'base %.0f MB' % (b / 1e6))
    tr = {}
    for s in w: tr.setdefault((s[0] - w[0][0]) // 20000, []).append(s[1])
    ks = sorted(tr)
    print('  20 s-window trough (min used - base) MB, first/middle/last of %d windows:' % len(ks), [round((min(tr[k]) - b) / 1e6, 1) for k in (ks[0], ks[len(ks) // 2], ks[-1])])
    print('  max of the first 157 samples: %.1f MB' % ((max(s[1] for s in w[:157]) - b) / 1e6))
