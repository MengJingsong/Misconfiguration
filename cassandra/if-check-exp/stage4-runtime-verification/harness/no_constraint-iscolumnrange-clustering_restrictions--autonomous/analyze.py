#!/usr/bin/env python3
"""Judge raw.csv / proof.txt / trace.txt of a run against the frozen prediction U1-U5 of
no_constraint-iscolumnrange-clustering_restrictions--autonomous (B2f) and the conclusions table (B2g).
Usage: analyze.py <raw-dir-plain> [<raw-dir-byteman>]   Prints PASS/FAIL lines and the key numbers."""
import csv, sys, re, statistics as st, collections
plain = sys.argv[1]; bm = sys.argv[2] if len(sys.argv) > 2 else None
res = []
def check(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))

rows = list(csv.DictReader(open(plain + '/raw.csv')))
cell = collections.defaultdict(list)          # (pass,state,N,arm) -> allocs
nrows = collections.defaultdict(set)
for r in rows:
    k = (r['pass'], r['state'], int(r['N']), r['arm']); cell[k].append(int(r['alloc'])); nrows[k].add(int(r['rows']))
Ns = sorted({k[2] for k in cell}); states = ['memtable', 'sstable']; arms = ['F1', 'F2', 'T1', 'T2', 'T3', 'C1', 'C2']
def med(p, s, n, a):
    if p == 'AB': return st.median(cell[('A', s, n, a)] + cell[('B', s, n, a)])
    return st.median(cell[(p, s, n, a)])

# known-answer and proof
proof = open(plain + '/proof.txt').read().splitlines()
check('instrument known-answer', any(l.startswith('CHECK alloc-known-answer') and l.endswith(' ok') for l in proof))
pl = [l for l in proof if l.startswith('PROOF')]
bad = []
for l in pl:
    d = dict(x.split('=', 1) for x in l.split()[1:])
    if d['arm'] in ('F1', 'F2', 'T1', 'T2', 'T3'):
        if d['isColumnRange'] != d['expect'] or d['filter'] != d['expectFilter'] or d['rows'] != '1' or d['ck1/ck2'] != '5/7': bad.append(l)
    elif d['arm'] == 'C1':
        if int(d['rows']) != int(d['n']): bad.append(l)
    elif d['arm'] == 'C2':
        if d['rows'] != '10': bad.append(l)
check('U1 branch proof (isColumnRange, filter class, one row 5/7) on every cell', len(bad) == 0 and len(pl) == len(Ns) * 2 * 2 * len(arms),
      f'{len(pl)} proof lines, {len(bad)} bad' + (' e.g. ' + bad[0] if bad else ''))
okrows = all(nrows[k] == ({1} if k[3] in ('F1','F2','T1','T2','T3') else {k[2]} if k[3] == 'C1' else {10}) for k in cell)
check('U1 every timed call returned the expected row count', okrows)
if bm:
    cnt = collections.defaultdict(collections.Counter); cur = None
    for l in open(bm + '/trace.txt'):
        l = l.strip()
        if l.startswith('MARK cell'):
            cur = dict(x.split('=') for x in l.split()[2:]); cur = (cur['pass'], cur['state'], int(cur['n']), cur['arm']); continue
        if l.startswith('ICR') and cur: cnt[cur][l.split()[1]] += 1
    exp = {'F1': 'false', 'F2': 'false', 'T1': 'true', 'T2': 'true', 'T3': 'true'}
    badc = []
    for k, c in cnt.items():
        if k[3] in exp:
            other = 'true' if exp[k[3]] == 'false' else 'false'
            if c[exp[k[3]]] < 10 or c[other] != 0: badc.append((k, dict(c)))
    ncells = sum(1 for k in cnt if k[3] in exp)
    check('U1 byteman: isColumnRange returns counted per cell, only the expected side, >= 10 each', not badc and ncells == len(Ns) * 2 * 2 * 5,
          f'{ncells} cells; bad={badc[:2]}')

# U2
for p in ('A', 'B', 'AB'):
    worst = (0, None)
    for s in states:
        for n in Ns:
            f1 = med(p, s, n, 'F1')
            for a in ('F2', 'T1', 'T2', 'T3'):
                rel = abs(med(p, s, n, a) - f1) / f1
                if rel > worst[0]: worst = (rel, (s, n, a, med(p, s, n, a), f1))
    check(f'U2 arms within 20% of F1 (pass {p})', worst[0] <= 0.20, f'max rel diff {worst[0]:.4f} at {worst[1]}')
# U3
for p in ('A', 'B', 'AB'):
    worst = None; ok = True
    for s in states:
        for a in ('F1', 'F2', 'T1', 'T2', 'T3'):
            ratio = med(p, s, Ns[-1], a) / med(p, s, Ns[0], a)
            if not (0.5 <= ratio <= 2): ok = False
            if worst is None or abs(ratio - 1) > abs(worst[0] - 1): worst = (ratio, s, a)
    check(f'U3 median(N={Ns[-1]})/median(N={Ns[0]}) in [0.5,2] for every F/T arm and state (pass {p})', ok, f'largest deviation ratio {worst}')
# U4
for p in ('A', 'B', 'AB'):
    ok = True; det = []
    for s in states:
        c1h, c1l, f1h = med(p, s, Ns[-1], 'C1'), med(p, s, Ns[0], 'C1'), med(p, s, Ns[-1], 'F1')
        c2h, c2l = med(p, s, Ns[-1], 'C2'), med(p, s, Ns[0], 'C2')
        o = c1h >= 1_000_000 and c1h >= 50 * c1l and c1h >= 100 * f1h and c2h <= 0.1 * c1h and 0.5 <= c2h / c2l <= 2
        ok &= o; det.append(f'{s}: C1 {c1h}/{c1l} ({c1h/c1l:.1f}x) F1 {f1h} C1/F1 {c1h/f1h:.0f}x C2 {c2h}/{c2l} C2/C1 {c2h/c1h:.4f}')
    check(f'U4 controls moved (pass {p})', ok, '; '.join(det))
# U5
mx = 0; rg = 0; wc = None
for s in states:
    for n in Ns:
        for a in arms:
            ma, mb = med('A', s, n, a), med('B', s, n, a); pooled = med('AB', s, n, a)
            d = abs(ma - mb) / pooled
            if d > mx: mx, wc = d, (s, n, a, ma, mb)
            for p in 'AB':
                v = cell[(p, s, n, a)]; rg = max(rg, (max(v) - min(v)) / st.median(v))
check('U5 noise floor: pass A vs B medians within 5%', mx <= 0.05, f'largest {mx:.5f} at {wc}')
check('U5 repeats (max-min)/median <= 10%', rg <= 0.10, f'largest {rg:.5f}')

# B2g row 3: does D(N) grow with N?
print('--- D(N) = median(arm) - median(F1), pooled passes (bytes); relative to F1')
grow = False
for s in states:
    for a in ('F2', 'T1', 'T2', 'T3'):
        d = [med('AB', s, n, a) - med('AB', s, n, 'F1') for n in Ns]
        rel = [x / med('AB', s, n, 'F1') for x, n in zip(d, Ns)]
        floor = max(abs(med('A', s, n, a) - med('B', s, n, a)) for n in (Ns[0], Ns[-1]))
        g = abs(d[-1]) - abs(d[0]) > max(floor, 4096) and abs(rel[-1]) > 0.20
        grow |= g
        print(f'{s} {a}: D={d} rel={[round(x,4) for x in rel]} grows_beyond_floor={g}')
print('--- medians (pooled passes)')
for s in states:
    for a in arms:
        print(s, a, [int(med('AB', s, n, a)) for n in Ns])
print('SUMMARY all_pass=%s refuting_growth=%s' % (all(res), grow))
