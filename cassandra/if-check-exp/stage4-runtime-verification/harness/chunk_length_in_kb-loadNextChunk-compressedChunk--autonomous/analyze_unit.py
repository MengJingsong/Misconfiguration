#!/usr/bin/env python3
"""PASS/FAIL per frozen unit prediction (case file B2f + B2i). Usage: analyze_unit.py <raw dir>"""
import sys, glob, os
MiB = 1 << 20
rows = {}
for f in sorted(glob.glob(os.path.join(sys.argv[1], 'results-*.csv'))):
    for line in open(f):
        if line.startswith('#') or not line.strip():
            continue
        p = line.rstrip('\n').split(',', 14)
        k = ['arm','kind','n','wire','bufB','ccB','bufA','ccA','p0','pCtor','pPos','pClose','dataOk','ctorEx','posEx']
        d = dict(zip(k, p))
        for x in ['n','wire','bufB','ccB','bufA','ccA','p0','pCtor','pPos','pClose']:
            d[x] = int(d[x])
        rows[d['arm']] = d
res = []
def chk(name, ok, detail):
    res.append((name, 'PASS' if ok else 'FAIL', detail))
for arm, d in rows.items():
    n, L = d['n'], d['wire']
    if arm.startswith('cap'):
        continue
    if d['kind'] == 'natural':
        exp = int(1.5 * n)
        chk(arm + ' wire in [n+5, n+4+n/255+16]', n + 5 <= L <= n + 4 + n // 255 + 16, 'W=%d n=%d (W-n=%d)' % (L, n, L - n))
        chk(arm + ' ccAfter == int(1.5n)', d['ccA'] == exp, 'ccAfter=%d expected=%d' % (d['ccA'], exp))
        chk(arm + ' bufAfter == n', d['bufA'] == n, 'bufAfter=%d' % d['bufA'])
        chk(arm + ' decompressed bytes equal input, no exception', d['dataOk'] == 'yes' and d['posEx'] == 'pos:', 'dataOk=%s %s' % (d['dataOk'], d['posEx']))
        chk(arm + ' pool delta after position ~ n + ccAfter (1 MiB)', abs((d['pPos'] - d['p0']) - (n + d['ccA'])) <= MiB, 'delta=%d expected=%d' % (d['pPos'] - d['p0'], n + d['ccA']))
        chk(arm + ' pool delta after close ~ 0 (1 MiB)', abs(d['pClose'] - d['p0']) <= MiB, 'delta=%d' % (d['pClose'] - d['p0']))
    elif d['kind'] == 'hand':
        exp = n if L <= n else max(int(1.5 * n), L)
        chk(arm + ' ccAfter == %d' % exp, d['ccA'] == exp, 'ccAfter=%d' % d['ccA'])
        chk(arm + ' bufAfter == n', d['bufA'] == n, 'bufAfter=%d' % d['bufA'])
        chk(arm + ' pool delta after position ~ n + ccAfter (1 MiB)', abs((d['pPos'] - d['p0']) - (n + d['ccA'])) <= MiB, 'delta=%d expected=%d' % (d['pPos'] - d['p0'], n + d['ccA']))
        chk(arm + ' pool delta after close ~ 0 (1 MiB)', abs(d['pClose'] - d['p0']) <= MiB, 'delta=%d' % (d['pClose'] - d['p0']))
    elif d['kind'] == 'ratio11':
        chk(arm + ' ccAfter == n (raw path, no regrow)', d['ccA'] == n, 'ccAfter=%d' % d['ccA'])
        chk(arm + ' bufAfter == n and bytes equal input', d['bufA'] == n and d['dataOk'] == 'yes' and d['posEx'] == 'pos:', 'bufAfter=%d dataOk=%s %s' % (d['bufA'], d['dataOk'], d['posEx']))
        chk(arm + ' pool delta after position ~ 2n (1 MiB)', abs((d['pPos'] - d['p0']) - 2 * n) <= MiB, 'delta=%d' % (d['pPos'] - d['p0']))
        chk(arm + ' pool delta after close ~ 0 (1 MiB)', abs(d['pClose'] - d['p0']) <= MiB, 'delta=%d' % (d['pClose'] - d['p0']))
DBM = 'Direct buffer memory'
if 'cap_wire32MiB' in rows:
    d = rows['cap_wire32MiB']
    chk('cap_wire32MiB (16m): ctor ok, OOM "Direct buffer memory" in position, ccAfter 16384', d['ctorEx'] == 'ctor:' and DBM in d['posEx'] and d['ccA'] == 16384, 'ctor=%r pos=%r ccAfter=%d' % (d['ctorEx'], d['posEx'], d['ccA']))
if 'cap_natural16MiB_init' in rows:
    d = rows['cap_natural16MiB_init']
    chk('cap_natural16MiB_init (16m): constructor OOM "Direct buffer memory"', DBM in d['ctorEx'], 'ctor=%r' % d['ctorEx'])
if 'cap38_natural16MiB' in rows:
    d = rows['cap38_natural16MiB']
    chk('cap38_natural16MiB (38m): ctor ok, OOM at regrow (position)', d['ctorEx'] == 'ctor:' and DBM in d['posEx'], 'ctor=%r pos=%r' % (d['ctorEx'], d['posEx']))
if 'cap38_ratio11_16MiB' in rows:
    d = rows['cap38_ratio11_16MiB']
    chk('cap38_ratio11_16MiB (38m): ctor ok, no OOM, ccAfter 16 MiB, bytes equal', d['ctorEx'] == 'ctor:' and d['posEx'] == 'pos:' and d['ccA'] == 16 * MiB and d['dataOk'] == 'yes', 'ctor=%r pos=%r ccAfter=%d dataOk=%s' % (d['ctorEx'], d['posEx'], d['ccA'], d['dataOk']))
for r in res:
    print('%-5s %s | %s' % (r[1], r[0], r[2]))
print('SUMMARY pass=%d fail=%d arms=%d' % (sum(1 for r in res if r[1] == 'PASS'), sum(1 for r in res if r[1] == 'FAIL'), len(rows)))
