#!/usr/bin/env python3
"""Unit-tier analyzer for B2f/B2g (frozen text). Usage: analyze_unit.py <unit.txt> [R]. Prints EXPECTED lines and a B2g row class.
Rules fixed before run 1:
 groups   : every run rep returns exactly min(N,R) groups (B2f 1)
 pulled   : pulled - N <= 5 for finite N (B2f 2: N plus a small constant); NO_LIMIT pulls R
 retained : median used_after (run arms, nothing kept) across N within 5% of each other (B2f 3)
 alloc    : median alloc non-decreasing in N and alloc per pulled row within a factor 3 across N >= 100 (B2f 4)
 control  : ctl arm (rows cloned and kept): median (used_after - used_before) at NO_LIMIT >= 1 MB, and rises monotonically over N=100,1000,NO_LIMIT, and exceeds the largest noise swing (max|used_after-used_before| in the no-query noise reps) by 10x"""
import sys, re, statistics as st
f = sys.argv[1]; R = int(sys.argv[2]) if len(sys.argv) > 2 else None
L = open(f).read().splitlines()
kv = dict(l.split('=', 1) for l in L if re.match(r'^[A-Za-z_]+=', l))
R = R or int(kv['R'])
runs = {'run': {}, 'ctl': {}}; noise = []
for l in L:
    m = re.match(r'^(run|ctl) N=(\S+) (.*)$', l)
    if m:
        d = dict(x.split('=') for x in m.group(3).split())
        n = R * 10 if m.group(2) == 'NO_LIMIT' else int(m.group(2))
        runs[m.group(1)].setdefault(n, []).append({k: int(v) for k, v in d.items()})
    m = re.match(r'^noise rep=\d+ used_before=(\d+) used_after=(\d+)', l)
    if m: noise.append(abs(int(m.group(2)) - int(m.group(1))))
ok = True
def exp(name, cond, detail):
    global ok; ok &= bool(cond); print('EXPECTED %-10s %s  %s' % (name, 'MATCH' if cond else 'MISMATCH', detail))
print('R =', R, ' firsttrigger =', kv.get('firsttrigger')); 
if not kv.get('firsttrigger', '').startswith('OK') or kv.get('done') != '1':
    print('CLASS  invalid: first trigger failed or run incomplete'); sys.exit(2)
ns = sorted(runs['run']); med = lambda xs: st.median(xs)
exp('groups', all(r['groups'] == min(n, R) and r['counted'] >= 0 for n in ns for r in runs['run'][n]),
    {('NO' if n > R else n): sorted({r['groups'] for r in runs['run'][n]}) for n in ns})
exp('pulled', all((r['pulled'] - n <= 5 and r['pulled'] >= n) if n <= R else r['pulled'] == R for n in ns for r in runs['run'][n]),
    {('NO' if n > R else n): sorted({r['pulled'] for r in runs['run'][n]}) for n in ns})
ret = {n: med([r['used_after'] for r in runs['run'][n]]) for n in ns}
spread = (max(ret.values()) - min(ret.values())) / min(ret.values())
exp('retained', spread <= 0.05, 'median used_after (bytes) per N %s; spread %.2f%%' % ({('NO' if n > R else n): v for n, v in ret.items()}, spread * 100))
al = {n: med([r['alloc'] for r in runs['run'][n]]) for n in ns}
per = {n: al[n] / med([r['pulled'] for r in runs['run'][n]]) for n in ns if n >= 100}
exp('alloc', all(al[a] <= al[b] for a, b in zip(ns, ns[1:])) and max(per.values()) / min(per.values()) <= 3,
    'median alloc %s; bytes per pulled row (N>=100) %s' % ({('NO' if n > R else n): v for n, v in al.items()}, {('NO' if n > R else n): round(v) for n, v in per.items()}))
cd = {n: med([r['used_after'] - r['used_before'] for r in runs['ctl'][n]]) for n in sorted(runs['ctl'])}
big = [n for n in cd if n >= 100]
mono = all(cd[a] < cd[b] for a, b in zip(big, big[1:]))
ns_noise = max(noise) if noise else 0
exp('control', cd[max(cd)] >= 1e6 and mono and cd[max(cd)] >= 10 * max(ns_noise, 1),
    'ctl retained delta per N %s; largest no-query noise swing %d B' % ({('NO' if n > R else n): int(v) for n, v in cd.items()}, ns_noise))
print('CLASS', 'B2g row 1: confirmed (groups=min(N,R), retained flat, alloc scales with pulled, control moves)' if ok else
      'NOT row 1: see MISMATCH lines (groups mismatch -> trace wrong; retained not flat -> refuted; control mismatch -> not confirmed)')
sys.exit(0 if ok else 1)
