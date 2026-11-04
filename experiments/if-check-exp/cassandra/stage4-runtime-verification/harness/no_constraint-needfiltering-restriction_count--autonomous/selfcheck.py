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
al = defaultdict(list); nr = defaultdict(set)
for i, line in enumerate(open(d + '/plain/raw/raw.csv')):
    f = line.strip().split(',')
    if i == 0 or f[0] == 'pass': continue
    k = (f[2], int(f[1]), f[0]); al[k].append(int(f[4])); nr[k[:2]].add(int(f[5]))
cells = {(a, n) for (a, n, p) in al}; ns = sorted({n for a, n in cells}); big, small = ns[-1], ns[0]
hold('5 windows (R, Fp, Fx, C1, C2) x 3 N, 7 timed values in each pass', len(cells) == 15 and all(len(al[(a, n, p)]) == 7 for a, n in cells for p in 'AB'))
def m(a, n): return median(al[(a, n, 'A')] + al[(a, n, 'B')])
hold('rows: Fx returned 1 row, C1 N rows, C2 10 rows', all(nr[(a, n)] == ({1} if a == 'Fx' else {n} if a == 'C1' else {10}) for a, n in cells if a in ('Fx', 'C1', 'C2')))
p = open(d + '/plain/raw/proof.txt').read()
r_ok = len(re.findall(r'arm=R class=InvalidRequestException rejectedWithFilteringMessage=true', p))
f_ok = len(re.findall(r'arm=F needFiltering=true keyRange=true usesIndex=false line985=false rows=1 ck=5', p))
hold('proof: 6 rejections and 6 accepted-with-line-992 statements (3 N x 2 passes)', r_ok == 6 and f_ok == 6, f'{r_ok} {f_ok}')
cur = None; c = defaultdict(lambda: defaultdict(int))
for line in open(d + '/bm/raw/trace.txt'):
    line = line.strip()
    mm = re.match(r'MARK cell pass=(\w) n=(\d+) arm=(\w+)', line)
    if mm: cur = (mm.group(1), int(mm.group(2)), mm.group(3)); continue
    if cur and line.startswith('L992'): c[cur]['L992'] += 1
    if cur and line.startswith('NF '): c[cur]['NF' + line.split()[1]] += 1
hold('byteman: every R cell reaches line 992 and returns true >= 10 times and never false',
     all(c[(q, n, 'R')]['L992'] >= 10 and c[(q, n, 'R')]['NFtrue'] >= 10 and c[(q, n, 'R')]['NFfalse'] == 0 for q in 'AB' for n in ns))
hold('byteman: F cells evaluate the helper at most once (the test proof call)', all(c[(q, n, 'F')]['L992'] <= 1 and c[(q, n, 'F')]['NFtrue'] <= 1 for q in 'AB' for n in ns))
hold('recomputed W2: R <= 262144 B and ratio N-large/N-small in [0.8,1.25]', all(m('R', n) <= 262144 for n in ns) and 0.8 <= m('R', big) / m('R', small) <= 1.25, str([int(m('R', n)) for n in ns]))
hold('recomputed W3: Fx(large) >= 1e7, >= 20x Fx(small), >= 50x R(large)', m('Fx', big) >= 1e7 and m('Fx', big) >= 20 * m('Fx', small) and m('Fx', big) >= 50 * m('R', big), str([int(m('Fx', n)) for n in ns]))
hold('recomputed W4: C1 >= 20x, C2 <= 0.1 C1 at large and within [0.5,2] of own at small', m('C1', big) >= 20 * m('C1', small) and m('C2', big) <= 0.1 * m('C1', big) and 0.5 <= m('C2', big) / m('C2', small) <= 2,
     'C1 %s C2 %s' % ([int(m('C1', n)) for n in ns], [int(m('C2', n)) for n in ns]))
noise = max(abs(median(al[(a, n, 'A')]) - median(al[(a, n, 'B')])) / m(a, n) for a, n in cells)
spread = max((max(al[(a, n, q)]) - min(al[(a, n, q)])) / median(al[(a, n, q)]) for a, n in cells for q in 'AB')
hold('recomputed W5: pass-to-pass <= 5%, repeat spread <= 10%', noise <= 0.05 and spread <= 0.10, f'{noise:.5f} {spread:.5f}')
print('Fp medians', [int(m('Fp', n)) for n in ns], 'R medians', [int(m('R', n)) for n in ns])
print('SELFCHECK', 'all hold' if all(out) else 'FAILURES')
