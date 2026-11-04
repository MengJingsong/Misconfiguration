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
al = defaultdict(list); rt = defaultdict(list); nr = defaultdict(set)
for i, line in enumerate(open(d + '/plain/raw/raw.csv')):
    f = line.strip().split(',')
    if i == 0 or f[0] == 'pass': continue
    k = (f[2], int(f[1]), f[0]); al[k].append(int(f[4])); nr[k[:2]].add(int(f[5])); rt[k].append(int(f[6]))
cells = {(a, n) for (a, n, p) in al}; ns = sorted({n for a, n in cells})
hold('5 arms x 3 N, 7 timed calls in each pass', len(cells) == 15 and all(len(al[(a, n, p)]) == 7 for a, n in cells for p in 'AB'))
def am(a, n): return median(al[(a, n, 'A')] + al[(a, n, 'B')])
def rm(a, n): return median(rt[(a, n, 'A')] + rt[(a, n, 'B')])
exp_rows = lambda a, n: {'P': n, 'P2': n, 'A1': 1, 'A2': 1, 'C': 100}[a]
hold('every timed call: P/P2 N rows, A1/A2 1 row, C 100 rows', all(nr[(a, n)] == {exp_rows(a, n)} for a, n in cells))
p = open(d + '/plain/raw/proof.txt').read()
good = 0
for m in re.finditer(r'PROOF pass=\w n=(\d+) arm=(\w+) isAggregate=(\w+) expect=\w+ rows=(\d+) firstRow=(\S+)', p):
    n, a, agg, r, fr = int(m.group(1)), m.group(2), m.group(3), int(m.group(4)), m.group(5).strip('/').split('/')
    ok = (agg == ('true' if a[0] == 'A' else 'false')) and r == exp_rows(a, n)
    if a == 'A1': ok = ok and fr == [str(n - 1)]
    if a == 'A2': ok = ok and fr == [str(n - 1), '0']
    good += ok
hold('proof: 30 lines, isAggregate by arm name, rows and values (max = N-1, min = 0)', good == 30, f'{good} good')
# byteman, own parse
cur = None; c = defaultdict(lambda: defaultdict(int))
for line in open(d + '/bm/raw/trace.txt'):
    line = line.strip()
    m = re.match(r'MARK (prep|cell) (?:pass=\w )?n=(\d+) arm=(\w+)', line)
    if m: cur = (m.group(1), int(m.group(2)), m.group(3)); continue
    if cur and line.startswith('DA '): c[cur]['DA' + line.split()[1]] += 1
    if cur and line == 'AQP': c[cur]['AQP'] += 1
ok = True
for (kind, n, a), v in c.items():
    if a == 'P' and sum(v.values()): ok = False
    if a in ('P2', 'C') and (v['DAtrue'] or v['AQP']): ok = False
    if a in ('A1', 'A2') and not v['DAtrue']: ok = False
hold('byteman: no doesAggregation call for P, never true for P2/C, true for A1/A2; no aggregate pager for P/P2/C', ok)
hold('byteman: aggregate pager entered >= 10 times in every A1/A2 run cell', all(v['AQP'] >= 10 for (k, n, a), v in c.items() if k == 'cell' and a in ('A1', 'A2')))
big, small = ns[-1], ns[0]
hold('recomputed V2: P/P2 retained >= 4e6 B at largest N and >= 50x smallest; A1/A2 <= 2048 B and flat',
     all(rm(a, big) >= 4e6 and rm(a, big) >= 50 * rm(a, small) for a in ('P', 'P2')) and all(max(rm(a, n) for n in ns) <= 2048 and max(rm(a, n) for n in ns) <= 1.5 * min(rm(a, n) for n in ns) for a in ('A1', 'A2')),
     str({a: [int(rm(a, n)) for n in ns] for a in ('P', 'P2', 'A1', 'A2', 'C')}))
hold('recomputed V3: allocation >= 10x from smallest to largest N for P/P2/A1/A2; A1/A2 >= 0.3 P2 for N >= 10000',
     all(am(a, big) >= 10 * am(a, small) for a in ('P', 'P2', 'A1', 'A2')) and all(am(a, n) >= 0.3 * am('P2', n) for a in ('A1', 'A2') for n in ns if n >= 10000),
     str({a: [int(am(a, n)) for n in ns] for a in ('P', 'P2', 'A1', 'A2', 'C')}))
hold('recomputed V4: C retained <= 0.01 P and alloc <= 0.1 P at largest N, alloc within [0.5,2] of own at smallest N',
     rm('C', big) <= 0.01 * rm('P', big) and am('C', big) <= 0.1 * am('P', big) and 0.5 <= am('C', big) / am('C', small) <= 2)
noise = max(abs(median(al[(a, n, 'A')]) - median(al[(a, n, 'B')])) / am(a, n) for a, n in cells)
spread = max((max(al[(a, n, q)]) - min(al[(a, n, q)])) / median(al[(a, n, q)]) for a, n in cells for q in 'AB')
rdiff = max(abs(median(rt[(a, n, 'A')]) - median(rt[(a, n, 'B')])) / max(1, rm(a, n)) for a, n in cells)
hold('recomputed V5: pass-to-pass <= 5%, repeat spread <= 10%, retained passes within 1%', noise <= 0.05 and spread <= 0.10 and rdiff <= 0.01, f'{noise:.5f} {spread:.5f} {rdiff:.6f}')
print('SELFCHECK', 'all hold' if all(out) else 'FAILURES')
