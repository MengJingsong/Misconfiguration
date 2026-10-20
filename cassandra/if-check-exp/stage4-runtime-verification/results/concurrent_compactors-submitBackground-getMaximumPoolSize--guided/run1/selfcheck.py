#!/usr/bin/env python3
"""Re-derives the cluster readings from the raw samples.csv of each label (independent of cluster-run.py's own RESULT lines)."""
import csv, glob, os, re, sys
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cluster')
BASE = 8596623858          # ks1 bytes after the restore, from idle/summary.txt (BASELINE line)
PER = 1074250132           # one table's four Data.db files, from every INPUT line
out = []
for l in ['idle', 'n1', 'n2a', 'n2b', 'n2c', 'n4', 'n8', 'ctl8', 'ctl8r', 'ctl8a']:
    rows = list(csv.reader(open(f'{R}/{l}/samples.csv')))[1:]
    t = [float(r[0]) for r in rows]; b = [int(r[1]) for r in rows]; k = [int(r[3]) for r in rows]
    base_line = [x for x in open(f'{R}/{l}/summary.txt') if x.startswith('BASELINE')][0]
    base = int(re.search(r'ks1 bytes (\d+)', base_line).group(1))
    peak = max(b) - base
    out.append(f'{l:6s} samples {len(rows):4d}  baseline {base}  (== BASE: {base == BASE})  peak_extra {peak:>12d}  = {peak / PER:5.2f} x one compaction  peak_running {max(k)}  last_running {k[-1]}')
print('\n'.join(out))
d = {l: max(int(r[1]) for r in list(csv.reader(open(f'{R}/{l}/samples.csv')))[1:]) - BASE for l in ['n2a', 'n2b', 'n2c']}
band = max(d.values()) - min(d.values())
print(f'noise band (range of the three default runs): {band} bytes = {band / PER:.3f} compaction; n1..n8 peaks:')
for l in ['n1', 'n2a', 'n4', 'n8']:
    p = max(int(r[1]) for r in list(csv.reader(open(f'{R}/{l}/samples.csv')))[1:]) - BASE
    print(f'  {l}: {p}  (peak at 8 minus peak at 1 = {max(int(r[1]) for r in list(csv.reader(open(R + "/n8/samples.csv")))[1:]) - max(int(r[1]) for r in list(csv.reader(open(R + "/n1/samples.csv")))[1:])}, band x 2 = {2 * band})')
