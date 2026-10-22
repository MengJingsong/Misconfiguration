#!/usr/bin/env python3
"""B2f/B2g checks (with audit amendment R4's definitions) for the unit tier of
tombstone_failure_threshold-countTombstone-tombstones--autonomous. usage: unit-analyze.py tft-unit.tsv [--shakedown]
Prints one EXPECTED line per check and the B2g row the readings match."""
import sys
rows = [l.rstrip('\n').split('\t') for l in open(sys.argv[1])][1:]
N = 300 if '--shakedown' in sys.argv else 30000
MAX = 2**31 - 1
if not rows:
    sys.exit('MATCHED: none (no rows in the tsv: the test did not run to completion)')
d = {}
for r in rows:
    pk, T, out, cnt, rb, unf, med, mn, mx = r
    d[(int(pk), int(T))] = dict(out=out, cnt=int(cnt), rb=int(rb), unf=int(unf), a=int(med), mn=int(mn), mx=int(mx))
Ts = sorted({t for (_, t) in d})
below = [t for t in Ts if t < N]; above = [t for t in Ts if t >= N]
res = {'yes': 0, 'no': 0}
def ex(desc, c):
    res['yes' if c else 'no'] += 1
    print(f'EXPECTED: {desc} — {"yes" if c else "NO"}')
    return c
A = lambda pk, t: d[(pk, t)]['a']
MB = 1e6
s = d[(0, MAX)]['rb'] / N if d[(0, MAX)]['rb'] > 0 else float('nan')
print(f'pk0 resp_bytes at T=MAX {d[(0, MAX)]["rb"]}; s = {s:.1f} B per tombstone')
for t in Ts:
    print(f'  pk0 T={t}: {d[(0,t)]["out"]} count={d[(0,t)]["cnt"]} A={A(0,t)/MB:.2f} MB (min {d[(0,t)]["mn"]/MB:.2f}, max {d[(0,t)]["mx"]/MB:.2f}); '
          f'A/(s*min(T+1,N)) = {A(0,t)/(s*min(t+1,N)):.2f}; pk1 A={A(1,t)/MB:.2f} MB')
# --- R4 decisive criteria for B2g row 1
c1 = ex('pk0 throws (TOE) exactly for T < N, with count = T+1', all((d[(0,t)]['out'] == 'TOE') == (t < N) for t in Ts)
        and all(d[(0,t)]['cnt'] == t + 1 for t in below))
c2 = ex('A(T) strictly increasing over the T < N values ' + str(below), all(A(0,a) < A(0,b) for a, b in zip(below, below[1:])))
c3 = ex(f'A(lowest T) <= 0.10 x A(MAX) (ratio {A(0,below[0])/A(0,MAX):.4f})', A(0, below[0]) <= 0.10 * A(0, MAX))
c4 = ex('A(N-1), A(N), A(default) within +-10% of A(MAX) (' + ', '.join(f'{A(0,t)/A(0,MAX):.3f}' for t in [N-1] + above[:-1]) + ')',
        all(abs(A(0,t)/A(0,MAX) - 1) <= 0.10 for t in [N-1] + above[:-1]))
c5 = ex('every OK read has unfiltered_in_resp = N', all(v['unf'] == N for v in d.values() if v['out'] == 'OK'))
p1 = [A(1,t) for t in Ts]
c6 = ex(f'pk1: all OK and max/min of A <= 1.10 ({max(p1)/min(p1):.3f})', all(d[(1,t)]['out'] == 'OK' for t in Ts) and max(p1)/min(p1) <= 1.10)
row1 = all([c1, c2, c3, c4, c5, c6])
# --- sub-predictions (B2f), reported, not decisive
if not '--shakedown' in sys.argv:
    ex(f'sub: A(10k)/A(1k) in 7-13 ({A(0,10000)/A(0,1000):.2f})', 7 <= A(0,10000)/A(0,1000) <= 13)
    ex(f'sub: A(20k)/A(10k) in 1.6-2.4 ({A(0,20000)/A(0,10000):.2f})', 1.6 <= A(0,20000)/A(0,10000) <= 2.4)
    ex('sub: 2 x s x min(T+1,N) <= A(T) <= 6 x s x min(T+1,N) for every T', all(2 <= A(0,t)/(s*min(t+1,N)) <= 6 for t in Ts))
    ex(f'sub: A(1k) in 2-6 MB ({A(0,1000)/MB:.2f})', 2e6 <= A(0,1000) <= 6e6)
    ex(f'sub: A(MAX) in 60-190 MB ({A(0,MAX)/MB:.2f})', 60e6 <= A(0,MAX) <= 190e6)
    ex(f'sub: resp_bytes at T>=N in 30-32 MB ({d[(0,MAX)]["rb"]/MB:.2f})', all(30e6 <= d[(0,t)]['rb'] <= 32e6 for t in above))
    ex(f'sub: pk1 resp_bytes 30-32 MB ({d[(1,MAX)]["rb"]/MB:.2f})', all(30e6 <= d[(1,t)]['rb'] <= 32e6 for t in Ts))
ex(f'sub: A(MAX) > A(lowest T) (positive control moves)', A(0, MAX) > A(0, below[0]))
# --- row decision
if row1:
    row = 'B2g row 1 (claim confirmed at unit level)'
elif c1 and A(0, below[0]) >= 0.5 * A(0, MAX):
    row = 'B2g row 2 (refuted: abort does not save the allocation)'
elif not c1:
    row = 'B2g row 3 (mechanism differs; claim not tested)'
elif c1 and (A(0, below[0]) > 0.10 * A(0, MAX) or not c2):
    row = 'B2g R6 row (not confirmed: partial saving or broken order)'
elif not c6:
    row = 'B2g row 5 (pk1 varies: noise; rerun)'
else:
    row = 'no single row: see the NO lines'
print(f'MATCHED: {row}; EXPECTED yes={res["yes"]} NO={res["no"]}')
