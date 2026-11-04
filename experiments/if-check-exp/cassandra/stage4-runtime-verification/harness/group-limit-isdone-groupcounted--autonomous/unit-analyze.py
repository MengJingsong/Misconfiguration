#!/usr/bin/env python3
"""Unit tier (B2f/B2g) analysis of group-limit-isdone-groupcounted--autonomous.
usage: unit-analyze.py <g72-unit.txt> [--shakedown]
Reads the G72 lines of GroupByLimitMemoryTest, prints each frozen prediction as an `EXPECTED:` line with PASS/FAIL against the reading,
then the matched B2g row. Prediction thresholds are taken from the case file as amended 2026-10-27 (A2, A3, A4, A5); nothing here was tuned
to a reading. With --shakedown the group size is 2000 instead of 20000 (instrument check; not a reading)."""
import re, sys, statistics as st

path = sys.argv[1]
shake = '--shakedown' in sys.argv
N = 2000 if shake else 20000
BIGL = 20000 if shake else 100000          # the shakedown scales 100_000 down to 20_000
NONE = 'none'
rows = []
for line in open(path):
    if not line.startswith('G72 '):
        continue
    kind = line.split()[1]
    kv = dict(re.findall(r'(\w+)=(\S+)', line))
    kv['kind'] = kind
    kv['warm'] = '(warm-up)' in line
    rows.append(kv)

def num(x):
    return None if x in (None, 'none') else int(x)

W = [r for r in rows if r['kind'] == 'W']
E = [r for r in rows if r['kind'] == 'E' and not r['warm']]
C = [r for r in rows if r['kind'] == 'C' and not r['warm']]
Ls = ['1', '1000', str(BIGL), NONE]
Ps = [100, 1000, 10000]
bad = []

def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok:
        bad.append(name)
    return ok

def cell(ds, l, p, key):
    v = [int(r[key]) for r in E if r['ds'] == ds and r['L'] == l and int(r['P']) == p]
    return v

# 0. instrument check (first trigger): the white-box counter fires on the many-groups data, L=1, P=100
w0 = [r for r in W if r['ds'] == 'M' and r['L'] == '1' and int(r['P']) == 100]
ok0 = bool(w0) and w0[0]['isDone'] == 'true' and w0[0]['groups'] == '1'
check('instrument: many-groups L=1 P=100 white-box counter reports groups=1 isDone=True', ok0, w0[0] if w0 else 'missing')
if not ok0:
    print('FIRST-TRIGGER CHECK FAILED: stop.')

# B2f, single-group dataset S
for p in Ps:
    for l in Ls:
        rr = cell('S', l, p, 'rows'); sp = cell('S', l, p, 'subpages'); mx = cell('S', l, p, 'maxRowsPerSubpage')
        check(f'S L={l} P={p}: rows read = {N}', bool(rr) and all(x == N for x in rr), rr)
        check(f'S L={l} P={p}: rows per sub-page <= P', bool(mx) and all(x <= p for x in mx), mx)
        check(f'S L={l} P={p}: sub-pages = floor({N}/P)+1 = {N // p + 1} (A2)', bool(sp) and all(x == N // p + 1 for x in sp), sp)
        w = [r for r in W if r['ds'] == 'S' and r['L'] == l and int(r['P']) == p]
        check(f'S L={l} P={p}: white-box groups=0 isDone=False rowsCounted=P', bool(w) and w[0]['groups'] == '0' and w[0]['isDone'] == 'false' and int(w[0]['rowsCounted']) == p, w[0] if w else 'missing')
    means = {l: st.mean(cell('S', l, p, 'allocBytes')) for l in Ls if cell('S', l, p, 'allocBytes')}
    lo, hi = min(means.values()), max(means.values())
    check(f'S P={p}: allocated bytes agree across L within 10 percent', hi <= lo * 1.10, {k: int(v) for k, v in means.items()} | {'max/min': round(hi / lo, 3)})
# allocation vs P (informative: scales with P only in the per-sub-page transient size) -> printed, no threshold in B2f
for p in Ps:
    print(f'INFO: S L=1 P={p} allocBytes mean {int(st.mean(cell("S", "1", p, "allocBytes")))}')

# B2f, many-groups dataset M
for p in Ps:
    for l in Ls:
        rr = cell('M', l, p, 'rows'); gg = cell('M', l, p, 'groups')
        li = num(l)
        if li is None:
            li = 10**9
        if li < N:
            check(f'M L={l} P={p}: total rows = L or L+1 (A3)', bool(rr) and all(x in (li, li + 1) for x in rr), rr)
            check(f'M L={l} P={p}: groups = L', bool(gg) and all(x == li for x in gg), gg)
        else:
            check(f'M L={l} P={p}: limit not reached, all {N} rows read (A3)', bool(rr) and all(x == N for x in rr), rr)
        w = [r for r in W if r['ds'] == 'M' and r['L'] == l and int(r['P']) == p]
        if w and li < N:
            if li < p:
                check(f'M L={l} P={p}: white-box groups=L isDone=True', w[0]['isDone'] == 'true' and int(w[0]['groups']) == li, w[0])
            else:
                check(f'M L={l} P={p}: white-box stops on rowLimit: rowsCounted=P isDone=False', w[0]['isDone'] == 'false' and int(w[0]['rowsCounted']) == p, w[0])
# control (A4)
cr = {}
for l in (100, 1000, 10000):
    v = [r for r in C if int(r['L']) == l]
    cr[l] = (st.mean([int(r['allocBytes']) for r in v]) if v else None, [int(r['rows']) for r in v])
    check(f'control L={l}: rows read = L', bool(v) and all(x == l for x in cr[l][1]), cr[l])
ctrl_moved = all(cr[l][0] for l in cr) and cr[10000][0] >= 10 * cr[100][0] and all(all(x == l for x in cr[l][1]) for l in cr)
check('control moved (A4): rows == L and alloc(10000) >= 10 x alloc(100)', ctrl_moved, {l: int(cr[l][0]) for l in cr if cr[l][0]} | {'ratio': round(cr[10000][0] / cr[100][0], 1) if cr[100][0] else None})

# B2g
s_rows = {(l, p): cell('S', l, p, 'rows') for l in Ls for p in Ps}
confirmed_flat = all(all(x == N for x in s_rows[(l, p)]) and s_rows[(l, p)] for l in Ls for p in Ps) and \
    all(max(st.mean(cell('S', l, p, 'allocBytes')) for l in Ls) <= 1.10 * min(st.mean(cell('S', l, p, 'allocBytes')) for l in Ls) for p in Ps) and \
    all(max(cell('S', l, p, 'maxRowsPerSubpage')) == p for l in Ls for p in Ps)
early_stop = any(st.mean(s_rows[('1', p)] or [N]) < 0.9 * N for p in Ps)
follows_L = any(max(st.mean(cell('S', l, p, 'allocBytes')) for l in Ls) > 1.10 * min(st.mean(cell('S', l, p, 'allocBytes')) for l in Ls) for p in Ps)
mech = all(w['isDone'] == 'true' for w in W if w['ds'] == 'M' and w['L'] != NONE and int(w['L']) < int(w['P']) and int(w['L']) < N) and \
    all(x in (num(l), num(l) + 1) for l in Ls if num(l) and num(l) < N for p in Ps for x in cell('M', l, p, 'rows'))
reached = any(num(l) is not None and num(l) < N and w['isDone'] == 'true' for l in Ls for w in W if w['ds'] == 'M' and w['L'] == l)
print()
print(f'B2g facts: confirmed_flat={confirmed_flat} early_stop={early_stop} follows_L={follows_L} mechanism_ok={mech} control_moved={ctrl_moved} limit_reached_in_M={reached}')
if shake:
    print('SHAKEDOWN: instrument check only, not a reading.')
if not ctrl_moved:
    row = 'Positive control did not move -> Control invalid; the result is Not confirmed (B2g row 5)'
elif early_stop:
    row = 'Single-group rows read drop when L=1 -> Claim refuted (B2g row 2)'
elif follows_L:
    row = 'Allocated bytes grow with L at fixed P -> Claim refuted (B2g row 3)'
elif confirmed_flat and mech and reached:
    row = 'Single-group rows read and allocated bytes the same for every L, per-sub-page rows follow P; many-groups limit fires -> Claim confirmed (B2g rows 1 and 4)'
elif not reached:
    row = 'Limit never reached in the many-groups run -> Not confirmed (B2g row 6)'
else:
    row = 'No B2g row matches -> Not confirmed (no matching row)'
print('MATCHED ROW:', row)
print('FAILED EXPECTATIONS:', bad if bad else 'none')
