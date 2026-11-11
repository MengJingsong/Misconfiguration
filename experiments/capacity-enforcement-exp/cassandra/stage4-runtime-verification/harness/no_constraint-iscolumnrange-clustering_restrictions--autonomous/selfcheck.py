#!/usr/bin/env python3
"""Independent re-parse of the raw files of run 1 (does not import analyze.py; plain line parsing, no csv module).
Usage: selfcheck.py <run-dir>  (the dir that holds plain/raw and bm/raw)"""
import sys, re
from collections import defaultdict
d = sys.argv[1]; out = []
def hold(name, ok, note=''):
    out.append(ok); print(('HOLD ' if ok else 'FAIL ') + name + (' :: ' + note if note else ''))
def median(v):
    s = sorted(v); n = len(s); return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
# raw.csv by hand
vals = defaultdict(list); rowsets = defaultdict(set)
for i, line in enumerate(open(d + '/plain/raw/raw.csv')):
    f = line.strip().split(',')
    if i == 0 or f[0] == 'pass': continue
    vals[(f[1], int(f[2]), f[3], f[0])].append(int(f[5])); rowsets[(f[1], int(f[2]), f[3])].add(int(f[6]))
cells = {k[:3] for k in vals}
hold('every cell has 7 timed values in each of 2 passes', all(len(vals[k + (p,)]) == 7 for k in cells for p in 'AB'), f'{len(cells)} cells')
hold('7 arms x 3 N x 2 states = 42 cells', len(cells) == 42)
def pooled(s, n, a): return median(vals[(s, n, a, 'A')] + vals[(s, n, a, 'B')])
# branch proof, re-derived from proof.txt text
p = open(d + '/plain/raw/proof.txt').read()
bad = 0; n_ok = 0
for m in re.finditer(r'PROOF pass=(\w) state=(\w+) n=(\d+) arm=(\w+) isColumnRange=(\S+) expect=(\S+) filter=(\S+) expectFilter=(\S+) rows=(\d+) ck1/ck2=(\S+)', p):
    pas, s, n, arm, icr, exp, flt, eflt, nr, ck = m.groups()
    if arm[0] in 'FT':
        good = (icr == ('false' if arm[0] == 'F' else 'true')) and flt == ('ClusteringIndexNamesFilter' if arm[0] == 'F' else 'ClusteringIndexSliceFilter') and nr == '1' and ck == '5/7'
        n_ok += good; bad += (not good)
hold('proof: 60 F/T proof lines, each side/filter/row as the arm table says', bad == 0 and n_ok == 60, f'{n_ok} good, {bad} bad')
# re-derive the filter class from the arm name only, ignore expect fields: F -> names, T -> slice
# byteman trace, own parse
cur = None; tc = defaultdict(lambda: [0, 0])
for line in open(d + '/bm/raw/trace.txt'):
    line = line.strip()
    m = re.match(r'MARK cell pass=(\w) state=(\w+) n=(\d+) arm=(\w+)', line)
    if m: cur = (m.group(2), int(m.group(3)), m.group(4), m.group(1)); continue
    if cur and line.startswith('ICR'): tc[cur][0 if line.endswith('true') else 1] += 1
wrong = [k for k, (t, f) in tc.items() if (k[2][0] == 'F' and (t != 0 or f < 10)) or (k[2][0] == 'T' and (f != 0 or t < 10))]
hold('byteman: F-arm cells see only false returns, T-arm cells only true (>=10 each)', not wrong, f'{len([k for k in tc if k[2][0] in "FT"])} cells')
# the numbers
ns = sorted({k[1] for k in cells})
rel = max(abs(pooled(s, n, a) - pooled(s, n, 'F1')) / pooled(s, n, 'F1') for s in ('memtable', 'sstable') for n in ns for a in ('F2', 'T1', 'T2', 'T3'))
hold('recomputed: largest arm-vs-F1 relative difference <= 20%', rel <= 0.20, f'{rel:.4f}')
rat = max(abs(pooled(s, ns[-1], a) / pooled(s, ns[0], a) - 1) for s in ('memtable', 'sstable') for a in ('F1', 'F2', 'T1', 'T2', 'T3'))
hold('recomputed: N-ratio of every F/T arm within [0.5, 2]', all(0.5 <= pooled(s, ns[-1], a) / pooled(s, ns[0], a) <= 2 for s in ('memtable', 'sstable') for a in ('F1', 'F2', 'T1', 'T2', 'T3')), f'largest |ratio-1| = {rat:.4f}')
ctl = [(s, pooled(s, ns[-1], 'C1'), pooled(s, ns[0], 'C1'), pooled(s, ns[-1], 'C2'), pooled(s, ns[0], 'C2'), pooled(s, ns[-1], 'F1')) for s in ('memtable', 'sstable')]
hold('recomputed: controls moved (C1 >= 1e6, >= 50x its N-small, >= 100x F1; C2 <= 0.1 C1 and within [0.5,2] of its N-small)',
     all(c1 >= 1e6 and c1 >= 50 * c1l and c1 >= 100 * f1 and c2 <= 0.1 * c1 and 0.5 <= c2 / c2l <= 2 for _, c1, c1l, c2, c2l, f1 in ctl), str([tuple(int(x) if isinstance(x, (int, float)) else x for x in c) for c in ctl]))
noise = max(abs(median(vals[k + ('A',)]) - median(vals[k + ('B',)])) / pooled(*k) for k in cells)
spread = max((max(vals[k + (p,)]) - min(vals[k + (p,)])) / median(vals[k + (p,)]) for k in cells for p in 'AB')
hold('recomputed: noise floor (passes) <= 5% and repeat spread <= 10%', noise <= 0.05 and spread <= 0.10, f'pass-to-pass {noise:.5f}; repeat spread {spread:.5f}')
# rows returned by the timed calls
hold('timed calls returned 1 row (F/T), N rows (C1), 10 rows (C2)', all(rowsets[k] == ({1} if k[2][0] in 'FT' else {k[1]} if k[2] == 'C1' else {10}) for k in cells))
# Is anything a lie of the aggregation? absolute values
print('absolute F1 medians (memtable/sstable) per N:', {n: (int(pooled('memtable', n, 'F1')), int(pooled('sstable', n, 'F1'))) for n in ns})
print('SELFCHECK', 'all hold' if all(out) else 'FAILURES')
