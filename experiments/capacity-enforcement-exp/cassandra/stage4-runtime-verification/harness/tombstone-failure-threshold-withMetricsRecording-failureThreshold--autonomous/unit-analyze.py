#!/usr/bin/env python3
"""B2f/B2g checks (case-file amendments A2-A4, 2026-10-26) for the unit tier of
tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous. usage: unit-analyze.py tfm-unit.tsv [--shakedown]
Prints one EXPECTED line per check and the B2g row the readings match."""
import sys
SH = '--shakedown' in sys.argv
rows = [l.rstrip('\n').split('\t') for l in open(sys.argv[1])][1:]
N = 1200 if SH else 120000
MAX = 2**31 - 1
WARN = 5 if SH else 500
if not rows:
    sys.exit('MATCHED: none (no rows in the tsv: the test did not run to completion)')
d, ctl = {}, {}
for r in rows:
    arm, pk, T, out, cnt, rb, unf, med, mn, mx, fd, wd, ret = r
    v = dict(out=out, cnt=int(cnt), rb=int(rb), unf=int(unf), a=int(med), mn=int(mn), mx=int(mx), fd=int(fd), wd=int(wd), ret=int(ret))
    if arm == 'sweep':
        d[(int(pk), int(T))] = v
    else:
        ctl[arm] = v
Ts = sorted({t for (_, t) in d})
below = [t for t in Ts if t < N]            # aborting T values
atleast = [t for t in Ts if t >= N]
res = {'yes': 0, 'no': 0}
def ex(desc, c):
    res['yes' if c else 'no'] += 1
    print(f'EXPECTED: {desc} - {"yes" if c else "NO"}')
    return c
A = lambda pk, t: d[(pk, t)]['a']
MB = 1e6
rbmax = d[(0, MAX)]['rb']
print(f'pk0 T=MAX: {d[(0, MAX)]["out"]} resp_bytes {rbmax}; per tombstone s = {rbmax / N:.1f} B')
for t in Ts:
    v = d[(0, t)]
    print(f'  pk0 T={t}: {v["out"]} count={v["cnt"]} A={v["a"]/MB:.2f} MB (min {v["mn"]/MB:.2f}, max {v["mx"]/MB:.2f}) fail+{v["fd"]} warn+{v["wd"]} retained={v["ret"]} A/A(MAX)={v["a"]/A(0,MAX):.4f}; pk1 A={A(1,t)/MB:.2f} MB')
c1 = ex('c1 pk0 aborts (TOE) iff T < N, count exactly T+1', all((d[(0, t)]['out'] == 'TOE') == (t < N) for t in Ts)
        and all(d[(0, t)]['cnt'] == t + 1 for t in below))
c2 = ex('c2 A(T) strictly increasing over the aborting T ' + str(below), all(A(0, a) < A(0, b) for a, b in zip(below, below[1:])))
c3 = ex(f'c3 A(lowest T) <= 0.10 x A(MAX) (ratio {A(0, below[0]) / A(0, MAX):.4f})', A(0, below[0]) <= 0.10 * A(0, MAX))
ok_ts = [t for t in atleast if t != MAX]
c4 = ex('c4 A at T >= N within +-10% of A(MAX) (' + ', '.join(f'{A(0, t) / A(0, MAX):.3f}' for t in ok_ts) + ') and every OK read has N unfiltered items',
        all(abs(A(0, t) / A(0, MAX) - 1) <= 0.10 for t in ok_ts) and all(v['unf'] == N for k, v in d.items() if k[0] == 0 and v['out'] == 'OK'))
def metrics_ok():
    good = True
    for t in Ts:
        v = d[(0, t)]
        if t < N and v['fd'] != 5: good = False            # 5 repetitions abort
        if t >= N and v['fd'] != 0: good = False
        want_w = 5 if (WARN < N < t) else 0                 # completes with warn < count < T  (ReadCommand.java:639)
        if v['wd'] != want_w: good = False
    return good
c5 = ex('c5 tombstoneFailures +5 per aborting T, 0 otherwise; tombstoneWarnings +5 only where warn < N < T (T=N: +0, aborts: +0)', metrics_ok())
p1 = [A(1, t) for t in Ts]
c6 = ex(f'c6 pk1 all OK, no tombstone metrics, max/min of A <= 1.10 ({max(p1) / min(p1):.3f})',
        all(d[(1, t)]['out'] == 'OK' for t in Ts) and max(p1) / min(p1) <= 1.10 and all(d[(1, t)]['fd'] == 0 and d[(1, t)]['wd'] == 0 for t in Ts))
off, on = ctl.get('ctl-off'), ctl.get('ctl-1MiB')
if off and on:
    cc = ex(f'control: 1 MiB local_read_size_fail aborts (LRS) and its A ({on["a"]/MB:.2f} MB) < 0.8 x unrestricted A ({off["a"]/MB:.2f} MB), unrestricted reads OK',
            on['out'] == 'LRS' and off['out'] == 'OK' and on['a'] < 0.8 * off['a'])
else:
    cc = ex('control arms present', False)
# sub-predictions, reported, not decisive
ex(f'sub: A(MAX) > A(lowest T) (the sweep moves)', A(0, MAX) > A(0, below[0]))
ex(f'sub: resp_bytes at T >= N equal within 1% ({[d[(0, t)]["rb"] for t in atleast]})', len({round(d[(0, t)]["rb"] / rbmax, 2) for t in atleast}) == 1)
# row decision
if not cc:
    row = 'INVALID: positive control did not move (or arms missing) - tier invalid'
elif c1 and all([c2, c3, c4, c5, c6]):
    row = 'B2g row 1 (abort at T+1 for every T; usage at the abort follows T; claim confirmed at unit level)'
elif c1 and A(0, below[0]) >= 0.5 * A(0, MAX):
    row = 'B2g row 3 (retained/allocated heap the same across T: claim wrong for memory)'
elif any(v['out'] == 'OK' and v['cnt'] == -1 and k[0] == 0 and k[1] < N for k, v in d.items()):
    row = 'B2g row 2 (read succeeds with a count above T: claim wrong; check bypassed)'
elif c1:
    row = 'Not confirmed (partial): abort at T+1 holds but the usage criteria c2-c6 do not all hold (A4)'
else:
    row = 'Not confirmed (no matching row): c1 failed'
print(f'MATCHED: {row}; EXPECTED yes={res["yes"]} NO={res["no"]}')
