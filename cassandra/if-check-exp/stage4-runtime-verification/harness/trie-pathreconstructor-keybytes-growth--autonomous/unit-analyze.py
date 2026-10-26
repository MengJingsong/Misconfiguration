#!/usr/bin/env python3
"""Unit-tier analysis of trie-pathreconstructor-keybytes-growth--autonomous: B2f (1)-(7) as EXPECTED lines against tp33-unit.txt,
then the B2g row. usage: python3 -I unit-analyze.py <tp33-unit.txt>"""
import re, sys, collections

rows = []
for l in open(sys.argv[1]):
    if l.startswith('TP33 '):
        rows.append({k: v for k, v in (kv.split('=', 1) for kv in l[5:].split())})
I = lambda r, k: int(r[k])
pts = [r for r in rows if r['kind'] in ('raw', 'real', 'zero')]
mctl = [r for r in rows if r['kind'] == 'mctl']
conc = [r for r in rows if r['kind'] == 'conc']
res = {}


def check(name, expected, ok, detail):
    res[name] = ok
    print(f'EXPECTED {name}: {expected}')
    print(f'  {"HOLDS" if ok else "FAILS"}: {detail}')


print(f'points {len(pts)}, mctl {len(mctl)}, conc {len(conc)}')
# (1) cap bounds
bad = [r for r in pts if not ((I(r, 'maxPath') <= 32 and I(r, 'cap') == 32) or (I(r, 'maxPath') <= I(r, 'cap') <= 2 * I(r, 'maxPath')))]
check('B2f(1)', 'cap = 32 when P <= 32, else P <= cap <= 2P (P = longest path handed to mapContent), all points',
      not bad, f'{len(pts) - len(bad)}/{len(pts)} points; violations: {[(r["kind"], r["bt"], r["L"], r["maxPath"], r["cap"]) for r in bad[:5]]}')
badP = [r for r in pts if I(r, 'P') != I(r, 'maxPath')]
check('B2f(1b)', 'P computed at insert time equals the path the iterator walked', not badP, f'{len(badP)} mismatches')
# (2)
def pick(kind, bt, L):
    return [r for r in pts if r['kind'] == kind and r['bt'] == bt and I(r, 'L') == L]
raw = pick('raw', 'ON_HEAP', 65535); real = pick('real', 'ON_HEAP', 65535); zero = pick('zero', 'ON_HEAP', 65535)
ok2 = (bool(raw) and all(65535 <= I(r, 'cap') <= 131070 for r in raw)
       and bool(real) and all(I(r, 'P') > 65535 and 65536 < I(r, 'cap') <= 2 * I(r, 'P') for r in real)
       and bool(zero) and bool(real) and all(I(real[0], 'P') - 65535 <= I(r, 'P') - 65535 <= I(real[0], 'P') - 65535 + 2 for r in zero))
check('B2f(2)', 'L=65535: raw 65535<=cap<=131070; real random P>65535 and 65536<cap<=2P; all-zero key: L+c <= P <= L+c+2 (c from the real random key) [R9]',
      ok2, f'raw cap {[I(r,"cap") for r in raw][:1]}; real P {[I(r,"P") for r in real][:1]} cap {[I(r,"cap") for r in real][:1]}; zero P {[I(r,"P") for r in zero][:1]} cap {[I(r,"cap") for r in zero][:1]}')
# (3)
cs = collections.defaultdict(set)
for r in pts:
    if r['kind'] in ('real', 'zero'):
        cs[r['kind']].add(I(r, 'P') - I(r, 'L'))
creal = sorted(cs['real'])
ok3 = len(creal) == 1 and 8 <= creal[0] <= 14 and bool(cs['zero']) and all(creal[0] <= v <= creal[0] + 2 for v in cs['zero'])
check('B2f(3)', 'real random keys: c = P - L is one constant over L, 8 <= c <= 14; all-zero keys: P - L in [c, c+2] [R9]', ok3, f'P-L values {dict((k, sorted(v)) for k, v in cs.items())}')
# (4)
bad4 = [r for r in pts if I(r, 'onB') != I(r, 'onA') or I(r, 'offB') != I(r, 'offA')] + \
       [r for r in mctl if I(r, 'onB') != I(r, 'onA') or I(r, 'offB') != I(r, 'offA')] + [r for r in conc if I(r, 'onB') != I(r, 'onA')]
check('B2f(4)', 'sizeOnHeap()/sizeOffHeap() after the drain equal those before it, every row', not bad4,
      f'{len(pts) + len(mctl) + len(conc) - len(bad4)}/{len(pts) + len(mctl) + len(conc)} rows equal')
# (5)
ok5, det5 = True, []
for bt in ('ON_HEAP', 'OFF_HEAP'):
    a = [r for r in mctl if r['bt'] == bt and I(r, 'M') == 10000]; b = [r for r in mctl if r['bt'] == bt and I(r, 'M') == 100000]
    if not a or not b:
        ok5 = False; continue
    key = 'onB' if bt == 'ON_HEAP' else 'offB'
    ratio = I(b[0], key) / max(1, I(a[0], key))
    inband = all(I(x, 'maxPath') <= I(x, 'cap') <= 2 * I(x, 'maxPath') for x in (a[0], b[0]))
    det5.append(f'{bt}: {key} {I(a[0], key)} -> {I(b[0], key)} (x{ratio:.1f}); cap {I(a[0], "cap")} / {I(b[0], "cap")}; in band {inband}')
    ok5 = ok5 and ratio >= 5 and inband
check('B2f(5)', 'M 10k -> 100k: sizes rise >= 5x, cap stays inside P..2P (P = 100)', ok5, '; '.join(det5))
# (6)
ok6, n6 = True, 0
for r in pts:
    if r['bt'] == 'ON_HEAP':
        o = pick(r['kind'], 'OFF_HEAP', I(r, 'L'))
        n6 += 1
        if not o or any(I(x, 'cap') != I(r, 'cap') for x in o):
            ok6 = False
check('B2f(6)', 'cap identical for ON_HEAP and OFF_HEAP at the same kind and L', ok6, f'{n6} (kind, L) pairs compared')
# (7)
bad7 = [r for r in conc if I(r, 'allocMinPerThread') < I(r, 'capMin') or I(r, 'allocSum') < I(r, 'N') * I(r, 'capMin')]
check('B2f(7)', 'N threads: every thread allocates >= its cap; sum >= N x cap', bool(conc) and not bad7,
      f'{[(I(r, "N"), I(r, "capMin"), I(r, "allocSum"), I(r, "allocMinPerThread")) for r in conc if r.get("rep") == "1"]}')
# repetitions identical
reps = collections.defaultdict(set)
for r in pts:
    reps[(r['kind'], r['bt'], r['L'])].add((r['P'], r['cap'], r['onB'], r['offB']))
check('B2h-reps', 'the 3 repetitions of a grid point agree', all(len(v) == 1 for v in reps.values()), f'{sum(len(v) > 1 for v in reps.values())} points differ')
coverage = all(pick('real', bt, 65535) and pick('raw', bt, 65535) for bt in ('ON_HEAP', 'OFF_HEAP'))
print('\nMATCHED ROW (B2g):')
if not coverage or not ok5:
    print('  Not confirmed (L=65535 not reached or the M control did not move)')
elif not res['B2f(4)']:
    print('  Claim refuted: the trie sizes change when the iterator is drained')
elif not (res['B2f(1)'] and res['B2f(1b)']):
    print('  Mechanism mis-traced (cap outside P..2P)')
elif all(res[k] for k in res):
    print('  Claim confirmed (array not accounted, not limited, bounded only by the path length)')
else:
    print('  UNMATCHED: some B2f part fails (' + ', '.join(k for k, v in res.items() if not v) + ') - see the lines above; do not edit B2f')
