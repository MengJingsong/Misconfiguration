#!/usr/bin/env python3
"""Unit tier (B2f/B2g) analysis of group-by-limit-incrementGroupCount-groupLimit--autonomous.
usage: unit-analyze.py <l79-unit.txt> [--shakedown]
Reads the L79 lines of GroupLimitProbeTest, prints each frozen prediction as an `EXPECTED:` line with PASS/FAIL, then the matched B2g row.
Thresholds are those of the case file as amended 2026-10-27 (A3, A6, A7); nothing here was tuned to a reading. Sizes come from the START line,
so a shakedown at smaller sizes is checked with the same code (its output is an instrument check, not a reading)."""
import re, sys, statistics as st

path = sys.argv[1]
shake = '--shakedown' in sys.argv
rows = []
start = {}
for line in open(path):
    if not line.startswith('L79 '):
        continue
    kind = line.split()[1]
    kv = dict(re.findall(r'(\w+)=(\S+)', line))
    if kind == 'START':
        start = {k: int(v) for k, v in kv.items()}
        continue
    kv['kind'] = kind
    kv['warm'] = '(warm-up)' in line
    rows.append(kv)
M_PARTS, M_ROWS = start['mParts'], start['mRows']
W = [r for r in rows if r['kind'] == 'W']
E = [r for r in rows if r['kind'] == 'E' and not r['warm']]
C = [r for r in rows if r['kind'] == 'C' and not r['warm']]
GS = sorted({int(r['g']) for r in E})
PS = sorted({int(r['P']) for r in E})
RS = sorted({int(r['r']) for r in E if r['ds'] == 'S'})
bad = []


def check(name, ok, detail):
    print(f'EXPECTED: {name}: {"PASS" if ok else "FAIL"} ({detail})')
    if not ok:
        bad.append(name)
    return ok


def vals(ds, r, p, g, key):
    return [int(x[key]) for x in E if x['ds'] == ds and int(x['r']) == r and int(x['P']) == p and int(x['g']) == g]


def wb(ds, r, p, g):
    v = [x for x in W if x['ds'] == ds and int(x['r']) == r and int(x['P']) == p and int(x['g']) == g]
    return v[0] if v else None


def mean(v):
    return st.mean(v) if v else float('nan')


# 0. instrument check (first trigger): the white-box counter fires on M, g=1, smallest P
pmin = min(PS)
w0 = wb('M', M_ROWS, pmin, 1)
ok0 = w0 is not None and w0['isDone'] == 'true' and w0['groups'] == '1' and int(w0['rowsCounted']) == min(M_ROWS, pmin) if w0 else False
if w0 and M_ROWS > pmin:
    ok0 = w0['isDone'] == 'false'      # group of M_ROWS rows is larger than a sub-page: not closed in the first sub-page
    check(f'instrument: M g=1 P={pmin}: first sub-page holds {pmin} rows of the {M_ROWS}-row group, isDone False', ok0 and int(w0['rowsCounted']) == pmin, w0)
w1 = wb('M', M_ROWS, max(PS), 1)
if w1:
    ok1 = w1['isDone'] == 'true' and w1['groups'] == '1' and int(w1['rowsCounted']) == M_ROWS
    check(f'instrument (A6 4): M g=1 P={max(PS)} white-box groups=1 rowsCounted={M_ROWS} isDone True', ok1, w1)
    if not ok1:
        print('FIRST-TRIGGER CHECK FAILED: stop.')

# B2f (1)-(3) single huge group S
for r in RS:
    for p in PS:
        for g in GS:
            rr = vals('S', r, p, g, 'rows'); sp = vals('S', r, p, g, 'subpages'); mx = vals('S', r, p, g, 'maxRowsPerSubpage'); gr = vals('S', r, p, g, 'groups')
            check(f'S r={r} P={p} g={g}: rows read = {r}', bool(rr) and all(x == r for x in rr), rr)
            check(f'S r={r} P={p} g={g}: groups counted = 1', bool(gr) and all(x == 1 for x in gr), gr)
            check(f'S r={r} P={p} g={g}: sub-pages = floor({r}/P)+1 = {r // p + 1} (A3)', bool(sp) and all(x == r // p + 1 for x in sp), sp)
            check(f'S r={r} P={p} g={g}: rows per sub-page <= P', bool(mx) and all(x <= p for x in mx), mx)
            if r > p:
                w = wb('S', r, p, g)
                check(f'S r={r} P={p} g={g}: white-box groups=0 rowsCounted=P isDone False', w is not None and w['groups'] == '0' and w['isDone'] == 'false' and int(w['rowsCounted']) == p, w)
        al = {g: mean(vals('S', r, p, g, 'allocBytes')) for g in GS}
        check(f'S r={r} P={p}: allocated bytes agree across g within 10 percent', max(al.values()) <= 1.10 * min(al.values()), {k: int(v) for k, v in al.items()} | {'max/min': round(max(al.values()) / min(al.values()), 3)})
        pk = {g: mean(vals('S', r, p, g, 'peakPools')) for g in GS}
        rise = pk[GS[-1]] > 1.10 * pk[GS[0]] and all(pk[GS[i]] < pk[GS[i + 1]] for i in range(len(GS) - 1))
        check(f'S r={r} P={p}: peakPools max/min <= 1.5 and no monotone rise > 10 percent from g={GS[0]} to g={GS[-1]} (A6 3)', max(pk.values()) <= 1.5 * min(pk.values()) and not rise,
              {k: int(v) for k, v in pk.items()} | {'max/min': round(max(pk.values()) / min(pk.values()), 3)})
# B2f (4) many small groups M
for p in PS:
    r = {g: vals('M', M_ROWS, p, g, 'rows') for g in GS}
    for g in GS:
        exp = M_ROWS * g if g < M_PARTS else M_ROWS * M_PARTS
        gg = vals('M', M_ROWS, p, g, 'groups')
        check(f'M P={p} g={g}: rows pulled in [{exp}, {exp + 1}] (A6 4)', bool(r[g]) and all(exp <= x <= exp + 1 for x in r[g]), r[g])
        check(f'M P={p} g={g}: groups counted = min(g, {M_PARTS})', bool(gg) and all(x == min(g, M_PARTS) for x in gg), gg)
    a = {g: mean(vals('M', M_ROWS, p, g, 'allocBytes')) for g in GS}
    if p == max(PS) and 10 in a and 1000 in a:
        check('M P=10000: allocation at g=1000 at least 5x that at g=10 (A6 4)', a[1000] >= 5 * a[10], {k: int(v) for k, v in a.items()} | {'ratio': round(a[1000] / a[10], 1)})
# control (A6 5)
cr = {}
for n in sorted({int(r['n']) for r in C}):
    v = [r for r in C if int(r['n']) == n]
    cr[n] = (mean([int(r['allocBytes']) for r in v]), [int(r['rows']) for r in v])
    check(f'control n={n}: rows read = n', all(x == n for x in cr[n][1]), cr[n][1])
ns = sorted(cr)
ctrl_moved = len(ns) >= 2 and all(all(x == n for x in cr[n][1]) for n in ns) and cr[ns[-1]][0] >= 10 * cr[ns[0]][0]
check(f'control moved (A6 5): rows == n and alloc(n={ns[-1]}) >= 10 x alloc(n={ns[0]})', ctrl_moved, {n: int(cr[n][0]) for n in ns} | {'ratio': round(cr[ns[-1]][0] / cr[ns[0]][0], 1)})

# B2g facts
huge = [(r, p, g) for r in RS for p in PS for g in GS]
flat_rows = all(vals('S', r, p, g, 'rows') and all(x == r for x in vals('S', r, p, g, 'rows')) for r, p, g in huge)
flat_alloc = all(max(mean(vals('S', r, p, g, 'allocBytes')) for g in GS) <= 1.10 * min(mean(vals('S', r, p, g, 'allocBytes')) for g in GS) for r in RS for p in PS)
early_stop = any(mean(vals('S', r, p, GS[0], 'rows')) < 0.9 * r for r in RS for p in PS if r > p)
follows_g = any(max(mean(vals('S', r, p, g, 'allocBytes')) for g in GS) > 1.10 * min(mean(vals('S', r, p, g, 'allocBytes')) for g in GS)
                for r in RS for p in PS) and not flat_alloc
pk_ok = all(max(mean(vals('S', r, p, g, 'peakPools')) for g in GS) <= 1.5 * min(mean(vals('S', r, p, g, 'peakPools')) for g in GS) for r in RS for p in PS)
small_reached = all(wb('M', M_ROWS, max(PS), g) is None or True for g in GS)
mech = bool(w1) and w1['isDone'] == 'true' and all(vals('M', M_ROWS, p, g, 'groups') and all(x == g for x in vals('M', M_ROWS, p, g, 'groups')) for p in PS for g in GS if g < M_PARTS)
print()
print(f'B2g facts: flat_rows={flat_rows} flat_alloc={flat_alloc} peak_ok={pk_ok} early_stop={early_stop} follows_g={follows_g} mechanism_ok={mech} control_moved={ctrl_moved}')
if shake:
    print('SHAKEDOWN: instrument check only, not a reading.')
if not ctrl_moved:
    row = 'Positive control did not move -> Not confirmed (B2g last row)'
elif early_stop:
    row = 'Huge-group query with g=1 stops after about p rows -> claim wrong (B2g row 3)'
elif follows_g or not pk_ok:
    row = 'Peak heap or allocation grows with g at constant group size -> claim refuted (B2g row 4)' if follows_g else 'Peak pools out of band -> no matching row'
elif flat_rows and flat_alloc and mech:
    row = 'Huge-group rows pulled = r for all g, allocation and peak flat across g; small-group table consumes rows with g -> claim confirmed (B2g rows 1, 2, 5)'
else:
    row = 'No B2g row matches -> Not confirmed (no matching row)'
print('MATCHED ROW:', row)
print('FAILED EXPECTATIONS:', bad if bad else 'none')
