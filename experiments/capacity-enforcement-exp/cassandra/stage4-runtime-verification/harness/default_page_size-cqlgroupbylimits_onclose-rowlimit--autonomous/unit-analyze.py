#!/usr/bin/env python3
"""Unit tier (B2f/B2g) analysis of default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.
usage: unit-analyze.py <run-dir with unit-<K>/dps-unit.txt for K = 100 1000 10000 50000> [--shakedown]
Prints each frozen prediction (B2f as amended 2026-10-27, U1-U5) as an `EXPECTED:` line with PASS/FAIL against the reading, then the facts that
select a B2g row. Thresholds come from the case file; nothing here was tuned to a reading. --shakedown: 4000 rows (instrument check, not a reading)."""
import os, re, sys, statistics as st
D = sys.argv[1]; shake = '--shakedown' in sys.argv
N = 4000 if shake else 200000
KS = [100, 1000, 10000, 50000]
bad = []
def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok: bad.append(name)
    return ok
def parse(path):
    rows = []
    for line in open(path):
        if not line.startswith('DPS '): continue
        kv = dict(re.findall(r"(\w+)=('[^']*'|\S+)", line)); kv['kind'] = line.split()[1]; kv['warm'] = '(warm-up)' in line
        m = re.search(r' p=(\S+)', line); kv['p'] = m.group(1) if m else None
        rows.append(kv)
    return rows
data = {}
for k in KS:
    p = os.path.join(D, f'unit-{k}', 'dps-unit.txt')
    if os.path.exists(p): data[k] = parse(p)
mean_alloc = {}
for k, rows in data.items():
    start = [r for r in rows if r['kind'] == 'START']
    check(f'K={k}: the compiled constant read by reflection == {k}', bool(start) and start[0]['constant'] == str(k), start[0] if start else 'missing')
    L = [r for r in rows if r['kind'] == 'L']
    check(f'K={k}: limits string (client page size unset) == LIMIT {k}; with page size 250 == LIMIT 250; plain aggregate has no LIMIT',
          bool(L) and L[0]['gb_unset'] == f"'LIMIT {k}'" and L[0]['gb_250'] == "'LIMIT 250'" and L[0]['plain_unset'] == "''" and L[0]['plain_250'] == "''", L[0] if L else 'missing')
    for p, lim in (('unset', k), ('250', 250)):
        w = [r for r in rows if r['kind'] == 'W' and r['p'] == p]
        lim_eff = min(lim, N)
        check(f'K={k} p={p}: white-box first sub-read rowsCounted == {lim_eff}, isDone False', bool(w) and int(w[0]['rowsCounted']) == lim_eff and w[0]['isDone'] == 'false', w[0] if w else 'missing')
        e = [r for r in rows if r['kind'] == 'E' and r['p'] == p and not r['warm']]
        check(f'K={k} p={p}: total rows == {N} in every rep', bool(e) and all(int(r['rows']) == N for r in e), [r['rows'] for r in e])
        check(f'K={k} p={p}: max rows per sub-read == {lim_eff} (never +1)', bool(e) and all(int(r['maxRowsPerSubpage']) == lim_eff for r in e), [r['maxRowsPerSubpage'] for r in e])
        exp = N // lim + 1
        check(f'K={k} p={p}: sub-reads == floor({N}/{lim})+1 = {exp} (U2)', bool(e) and all(int(r['subpages']) == exp for r in e), [r['subpages'] for r in e])
        check(f'K={k} p={p}: sub-reads with exactly the limit == floor({N}/{lim}) = {N // lim}', bool(e) and all(int(r['atMax']) == N // lim for r in e), [r['atMax'] for r in e])
        if p == 'unset' and e:
            mean_alloc[k] = st.mean(int(r['meanAllocFullSubread']) for r in e)
    for p in ('unset', '250'):
        pr = [r for r in rows if r['kind'] == 'P' and r['p'] == p]
        check(f'K={k} plain aggregate p={p}: one raw read of all {N} rows, empty limits string', bool(pr) and int(pr[0]['rowsDrained']) == N and pr[0]['limits'] == "''", pr[0] if pr else 'missing')
    w = [r for r in rows if r['kind'] == 'W' and r['p'] == 'unset']
    if w:
        b = int(w[0]['firstReadBytes']); bs = int(w[0]['firstReadBytesCountStar']); lim = min(k, N)
        print(f'INFO: K={k}: first-read serialised bytes count(v) {b} ({b / lim:.1f} per row), count(*) {bs} ({bs / lim:.1f} per row)')
    print(f'INFO: K={k}: mean allocated bytes per full sub-read (unset) {mean_alloc.get(k)}')
if not shake and 100 in mean_alloc and 50000 in mean_alloc:
    r = mean_alloc[50000] / mean_alloc[100]
    check('U3: mean allocated bytes per full sub-read, ratio(50000)/ratio(100) in [100, 550]', 100 <= r <= 550, f'{r:.1f}')
if not shake and 1000 in data and 10000 in data:
    f = lambda k: int([r for r in data[k] if r['kind'] == 'W' and r['p'] == 'unset'][0]['firstReadBytes'])
    ratio = f(10000) / f(1000)
    check('first-read serialised size(10000)/size(1000) in [9, 11] (bytes follow the constant)', 9 <= ratio <= 11, f'{ratio:.3f}')
    check('first-read serialised bytes per row in [1024, 1120] at K=10000', 1024 <= f(10000) / 10000 <= 1120, f'{f(10000) / 10000:.1f}')
miss = [k for k in KS if k not in data]
print('MATCHED B2g row:', 'row 1 (rows per sub-read == constant, count as predicted, allocation scales: claim confirmed)' if not bad and not miss else f'NOT all predictions passed or values missing {miss} -> map to B2g rows or Not confirmed')
print('SUMMARY:', 'ALL PASS' if not bad and not miss else f'{len(bad)} FAIL: {bad}; missing {miss}')
