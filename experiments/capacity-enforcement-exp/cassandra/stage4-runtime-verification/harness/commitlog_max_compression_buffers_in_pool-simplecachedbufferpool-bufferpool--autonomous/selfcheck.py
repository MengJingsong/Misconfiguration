#!/usr/bin/env python3
"""Self-check (results section 5): re-reads the committed excerpts under results/<stem>/run1/ independently of the analyzers.
usage: selfcheck.py <results-run1-dir>"""
import re, sys
R = sys.argv[1]; MiB = 2 ** 20
for l in open(f'{R}/unit-readings.txt'):
    if 'O44 BASE' in l or 't=5s' in l or 'O44 AFTER' in l or 'retained=' in l:
        print('UNIT', re.sub(r'pool=\[[^]]*\] |writerTop=.*', '', l.strip())[24:])
ses = open(f'{R}/cluster-session.log').read()
for t in ('3', '6', '12', '24', 'mmap6'):
    blk = ses.split(f'=== value {t}:')[-1].split('=== value')[0]
    i0, s0, s1 = [int(re.search(rf'PHASE {k} (\d+)', blk).group(1)) for k in ('idle_start', 'stress_start', 'stress_end')]
    S = [list(map(int, l.split(',')[:5])) for l in open(f'{R}/samples-{t}.csv') if l[0].isdigit()]
    idle = sorted(r[1] for r in S if i0 <= r[0] < s0); pw = sorted(r[1] for r in S if s0 + 60000 <= r[0] <= s1)
    w = [r[3] for r in S if s0 <= r[0] <= s1]
    print('CLUSTER', t, 'idle min/max MiB', round(idle[0] / MiB, 1), round(idle[-1] / MiB, 1), 'plateau min/max MiB', round(pw[0] / MiB, 1),
          round(pw[-1] / MiB, 1), 'waits first/last in stress', w[0], w[-1], 'max segment files', max(r[4] for r in S if s0 <= r[0] <= s1))
