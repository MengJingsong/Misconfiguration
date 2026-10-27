#!/usr/bin/env python3
"""Unit tier (B2f/B2g) analysis of group-by-row-limit-incrementRowCount-rowsCounted--autonomous.
usage: unit-analyze.py <b78-unit.txt> [--shakedown]
Prints each frozen prediction (B2f as amended 2026-10-27, A5) as an `EXPECTED:` line with PASS/FAIL against the reading, then the matched B2g row.
Thresholds come from the case file; nothing here was tuned to a reading. --shakedown: group of 2000 rows (instrument check, not a reading)."""
import re, sys, statistics as st
path = sys.argv[1]
shake = '--shakedown' in sys.argv
N = 2000 if shake else 50000
rows = []
for line in open(path):
    if not line.startswith('B78 '):
        continue
    kv = dict(re.findall(r'(\w+)=(\S+)', line)); kv['kind'] = line.split()[1]; kv['warm'] = '(warm-up)' in line
    kv['p'] = re.search(r' p=(\S+)', line).group(1) if ' p=' in line else None
    rows.append(kv)
W = [r for r in rows if r['kind'] == 'W']; E = [r for r in rows if r['kind'] == 'E' and not r['warm']]
C = [r for r in rows if r['kind'] == 'C' and not r['warm']]; CB = [r for r in rows if r['kind'] == 'CB']
bad = []
def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok: bad.append(name)
    return ok
def eff(p): return 10000 if p == 'unset' else int(p)
Ps = ['1', '7', '1000', '10000', 'unset']
bytes_first = {}
for p in Ps:
    ep = eff(p)
    w = [r for r in W if r['p'] == p]
    check(f'p={p}: white-box first sub-read rowsCounted == {min(ep, N)}, groups == {0 if N >= ep else 1}, isDone False', bool(w) and int(w[0]['rowsCounted']) == min(ep, N) and w[0]['groups'] == ('0' if N >= ep else '1') and w[0]['isDone'] == 'false', w[0] if w else 'missing')
    if w: bytes_first[p] = int(w[0]['firstReadBytes'])
    e = [r for r in E if r['p'] == p]
    check(f'p={p}: total rows == {N} in every rep', bool(e) and all(int(r['rows']) == N for r in e), [r['rows'] for r in e])
    check(f'p={p}: max rows per sub-read == {min(ep, N)} (never {ep}+1)', bool(e) and all(int(r['maxRowsPerSubpage']) == min(ep, N) for r in e), [r['maxRowsPerSubpage'] for r in e])
    if N >= ep:
        check(f'p={p}: sub-reads with exactly p rows == floor({N}/{ep}) = {N // ep}, and at most one other non-empty sub-read', bool(e) and all(int(r['atMax']) == N // ep and int(r['nonEmpty']) - int(r['atMax']) in (0, 1) for r in e), [(r['atMax'], r['nonEmpty']) for r in e])
    exp = N // ep + (2 if p == '1' else 1)
    check(f'p={p}: sub-reads == {exp} (floor({N}/{ep})+1' + ('; +1 more at p=1: the group count 1 fills the top-level page, so a second client page makes one more empty sub-read, A10)' if p == '1' else ')'), bool(e) and all(int(r['subpages']) == exp for r in e), [r['subpages'] for r in e])
    if p == '1':
        check('p=1: client pages == 2 (A10)', bool(e) and all(int(r['pages']) == 2 for r in e), [r['pages'] for r in e])
if 'unset' in bytes_first and '10000' in bytes_first:
    check('paging unset == p=10000 in sub-read count', [r['subpages'] for r in E if r['p'] == 'unset'] == [r['subpages'] for r in E if r['p'] == '10000'], '')
if not shake:
    for p in ('1000', '10000'):
        bpr = bytes_first[p] / int(p)
        check(f'p={p}: first-read serialised bytes per row in [1024, 1120]', 1024 <= bpr <= 1120, f'{bytes_first[p]} bytes, {bpr:.1f}/row')
    ratio = bytes_first['10000'] / bytes_first['1000']
    check('size(10000)/size(1000) in [9, 11]', 9 <= ratio <= 11, f'{ratio:.3f}')
else:
    print('INFO: serialised bytes', bytes_first)
for p in ('7', '1000', '10000'):
    c = [r for r in C if r['p'] == p]; cb = [r for r in CB if r['p'] == p]
    check(f'control p={p}: rows == p', bool(c) and all(int(r['rows']) == min(int(p), N) for r in c), [r['rows'] for r in c])
    if p != '7' and cb and p in bytes_first:
        a, b = int(cb[0]['firstReadBytes']) / int(p), bytes_first[p] / int(p)
        check(f'control p={p}: serialised bytes per row within 5 percent of the GROUP BY read', abs(a - b) / b <= 0.05, f'control {a:.1f} vs group-by {b:.1f}')
for p in Ps:
    a = [int(r['allocBytes']) for r in E if r['p'] == p]
    if a: print(f'INFO: p={p}: thread-allocated bytes over the drain, mean {st.mean(a):.0f}')
print('MATCHED B2g row:', 'row 1 (max rows per sub-read == p, bytes linear in p: claim supported)' if not bad else 'NOT all predictions passed -> see FAIL lines; map to B2g rows or Not confirmed (no matching row)')
print('SUMMARY:', 'ALL PASS' if not bad else f'{len(bad)} FAIL: {bad}')
