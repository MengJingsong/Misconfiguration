#!/usr/bin/env python3
"""Judge raw.csv / proof.txt / trace.txt of a run against the frozen prediction W1-W5 of
no_constraint-needfiltering-restriction_count--autonomous (B2f) and the conclusions table (B2g).
Usage: analyze.py <raw-dir-plain> [<raw-dir-byteman>]"""
import csv, sys, collections, statistics as st
plain = sys.argv[1]; bm = sys.argv[2] if len(sys.argv) > 2 else None
res = []
def check(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ((' :: ' + detail) if detail else ''))
rows = list(csv.DictReader(open(plain + '/raw.csv')))
al = collections.defaultdict(list); nr = collections.defaultdict(set)
for r in rows:
    k = (r['pass'], int(r['N']), r['arm']); al[k].append(int(r['alloc'])); nr[k].add(int(r['rows']))
Ns = sorted({k[1] for k in al}); arms = ['R', 'Fp', 'Fx', 'C1', 'C2']
def med(p, n, a): return st.median(al[('A', n, a)] + al[('B', n, a)]) if p == 'AB' else st.median(al[(p, n, a)])
proof = open(plain + '/proof.txt').read().splitlines()
check('instrument known-answer', any(l.startswith('CHECK alloc-known-answer') and l.endswith(' ok') for l in proof))
pl = [l for l in proof if l.startswith('PROOF')]; bad = []
for l in pl:
    d = dict(x.split('=', 1) for x in l.split(' msg=')[0].split()[1:])   # the msg= tail has spaces
    if d['arm'] == 'R' and not (d['class'] == 'InvalidRequestException' and d['rejectedWithFilteringMessage'] == 'true'): bad.append(l)
    if d['arm'] == 'F' and not (d['needFiltering'] == 'true' and d['keyRange'] == 'true' and d['usesIndex'] == 'false' and d['line985'] == 'false' and d['rows'] == '1' and d['ck'] == '5'): bad.append(l)
check('W1 branch proof: R rejected with the filtering message; F accepted, needFiltering true by line 992, one row ck=5', not bad and len(pl) == len(Ns) * 2 * 2, f'{len(pl)} lines, {len(bad)} bad' + (' e.g. ' + bad[0] if bad else ''))
check('W1 F returned exactly 1 row in every timed call; controls returned N / 10 rows', all(nr[k] == ({1} if k[2] == 'Fx' else {k[1]} if k[2] == 'C1' else {10} if k[2] == 'C2' else {-1}) for k in al))
if bm:
    cur = None; cnt = collections.defaultdict(collections.Counter)
    for l in open(bm + '/trace.txt'):
        l = l.strip()
        if l.startswith('MARK'):
            f = l.split(); d = dict(x.split('=') for x in f[2:]); cur = (d['pass'], int(d['n']), d['arm']); continue
        if cur and (l.startswith('L992') or l.startswith('NF')): cnt[cur][l.split()[0] + (('_' + l.split()[1]) if l.startswith('NF') else '')] += 1
    badc = []
    for p in 'AB':
        for n in Ns:
            r = cnt[(p, n, 'R')]; f = cnt[(p, n, 'F')]
            if r['L992'] < 10 or r['NF_true'] < 10 or r['NF_false']: badc.append((p, n, 'R', dict(r)))
            if f['L992'] > 1 or f['NF_true'] > 1 or f['NF_false']: badc.append((p, n, 'F', dict(f)))
    check('W1 byteman: line 992 reached and needFiltering true >= 10 per R cell; at most the one proof call per F cell', not badc, f'bad={badc[:3]}')
for p in ('A', 'B', 'AB'):
    big, small = Ns[-1], Ns[0]
    ok = all(med(p, n, 'R') <= 262144 for n in Ns) and 0.8 <= med(p, big, 'R') / med(p, small, 'R') <= 1.25
    check(f'W2 rejected arm flat (pass {p})', ok, f'R {[int(med(p, n, "R")) for n in Ns]} ratio {med(p, big, "R")/med(p, small, "R"):.3f}')
    ok = med(p, big, 'Fx') >= 10_000_000 and med(p, big, 'Fx') >= 20 * med(p, small, 'Fx') and med(p, big, 'Fx') >= 50 * med(p, big, 'R')
    check(f'W3 accepted arm follows the data (pass {p})', ok, f'Fx {[int(med(p, n, "Fx")) for n in Ns]} Fx/R@big {med(p, big, "Fx")/med(p, big, "R"):.0f}x Fp {[int(med(p, n, "Fp")) for n in Ns]}')
    ok = med(p, big, 'C1') >= 20 * med(p, small, 'C1') and med(p, big, 'C2') <= 0.1 * med(p, big, 'C1') and 0.5 <= med(p, big, 'C2') / med(p, small, 'C2') <= 2
    check(f'W4 controls moved (pass {p})', ok, f'C1 {[int(med(p, n, "C1")) for n in Ns]} C2 {[int(med(p, n, "C2")) for n in Ns]}')
mx = 0; rg = 0; wc = None
for n in Ns:
    for a in arms:
        d = abs(med('A', n, a) - med('B', n, a)) / med('AB', n, a)
        if d > mx: mx, wc = d, (n, a, med('A', n, a), med('B', n, a))
        for p in 'AB':
            v = al[(p, n, a)]; rg = max(rg, (max(v) - min(v)) / st.median(v))
check('W5 noise: passes within 5%', mx <= 0.05, f'largest {mx:.5f} at {wc}')
check('W5 repeats (max-min)/median <= 10%', rg <= 0.10, f'largest {rg:.5f}')
print('--- medians (pooled) per N', Ns)
for a in arms: print(a, [int(med('AB', n, a)) for n in Ns])
print('SUMMARY all_pass=%s' % all(res))
