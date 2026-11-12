#!/usr/bin/env python3
"""Cluster-tier analyzer (B3f/B3g as amended M9; windows and thresholds fixed 2026-11-11 before any cluster reading).
usage: cluster-analyze.py <outdir>.  Reads session.log (PHASE lines, epoch ms) and samples-<v>.csv.
Row logic: row 1 (supported) = every compressed N: flat, waits grow, no overshoot; consecutive pairwise steps within ±15 % of ΔN×64 MiB;
mmap control holds. Confirmed additionally needs every absolute band (M9) to hold; row 1 with a band missed is reported as
'row 1 matched, B3f band missed' (Partial). Rows 2-5 as in B3g/M9; otherwise 'Not confirmed (no matching row)'."""
import re, statistics, sys
OUT = sys.argv[1]; MiB = 1 << 20; SEG = 64 * MiB
ses = open(f'{OUT}/session.log').read()
def phases(tag):
    blk = ses.split(f'=== value {tag}:')[-1].split('=== value')[0]   # last attempt of this value (fix D3: N=24 was restarted)
    g = lambda k: int(re.search(rf'PHASE {k} (\d+)', blk).group(1))
    return g('idle_start'), g('stress_start'), g('stress_end')
def rows(tag):
    out = []
    for l in open(f'{OUT}/samples-{tag}.csv'):
        p = l.strip().split(',')
        if len(p) >= 5 and p[0].isdigit() and p[1].isdigit():
            out.append((int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4])))
    return out
R = {}
fails = 0
def chk(name, ok, d):
    global fails
    print(f"{'PASS' if ok else 'FAIL'} {name}: {d}"); fails += (not ok); return ok
tags = [t for t in ('3', '6', '12', '24', 'mmap6') if f'=== value {t}:' in ses]
for t in tags:
    i0, s0, s1 = phases(t); S = rows(t)
    idle = [r for r in S if i0 <= r[0] < s0]; st = [r for r in S if s0 <= r[0] <= s1]; pw = [r for r in S if s0 + 60000 <= r[0] <= s1]
    base = statistics.median(r[1] for r in idle); plat = statistics.median(r[1] for r in pw)
    rng = max(r[1] for r in pw) - min(r[1] for r in pw); peak = max(r[1] for r in st)
    w_start = max([r[3] for r in S if r[0] <= s0] or [st[0][3]]); w_end = st[-1][3]
    R[t] = dict(base=base, plat=plat, net=plat - base, rng=rng, peak=peak - base, waits=w_end - w_start, nidle=len(idle), npw=len(pw), nst=len(st),
                segmax=max(r[4] for r in st), cnt=(statistics.median(r[2] for r in idle), statistics.median(r[2] for r in pw)))
    print(f"INFO {t}: idle n={len(idle)} stress n={len(st)} plateau-window n={len(pw)} baseline={base/MiB:.1f} MiB plateau={plat/MiB:.1f} MiB "
          f"net={(plat-base)/MiB:.1f} MiB range={rng/MiB:.1f} MiB peak-base={(peak-base)/MiB:.1f} MiB waitsΔ={w_end-w_start} "
          f"direct Count idle/plateau={R[t]['cnt']} max segment files={R[t]['segmax']}")
comp = [t for t in ('3', '6', '12', '24') if t in R]
ok_flat = ok_wait = ok_over = ok_band = True; over = False; notreached = []
for t in comp:
    n = int(t); r = R[t]
    ok_flat &= chk(f'N={n} flat (range ≤ 96 MiB)', r['rng'] <= 96 * MiB, f"{r['rng']/MiB:.1f} MiB")
    ok_wait &= chk(f'N={n} waits grow (≥ 1)', r['waits'] >= 1, str(r['waits']))
    o = r['peak'] <= (n + 2) * SEG + 32 * MiB
    ok_over &= chk(f'N={n} never exceeding (peak-base ≤ (N+2)×64+32 MiB)', o, f"{r['peak']/MiB:.1f} ≤ {((n+2)*64+32)}")
    over |= not o
    lo, hi = (n - 2) * SEG, (n - 2) * SEG + 160 * MiB
    ok_band &= chk(f'N={n} band (N-2)×64+[0,160] MiB', lo <= r['net'] <= hi, f"net {r['net']/MiB:.1f} in [{lo/MiB:.0f},{hi/MiB:.0f}]")
    if r['waits'] == 0 and r['net'] < (n - 2) * SEG: notreached.append(n)
ok_pair = True
for a, b in (('3', '6'), ('6', '12'), ('12', '24')):
    if a in R and b in R:
        d = R[b]['plat'] - R[a]['plat']; e = (int(b) - int(a)) * SEG
        ok_pair &= chk(f'pairwise {a}→{b} within ±15% of {e//MiB} MiB', abs(d - e) <= 0.15 * e, f"{d/MiB:.1f} MiB ({d/e:.3f}×)")
nochange = '24' in R and '3' in R and (R['24']['plat'] - R['3']['plat']) < 0.5 * 21 * SEG
mm_ok = mm_invalid = None
if 'mmap6' in R and '6' in R:
    mm = R['mmap6']['net']
    mm_ok = chk('mmap control: plateau-base ≤ 64 MiB', mm <= 64 * MiB, f"{mm/MiB:.1f} MiB")
    mm_invalid = mm >= R['6']['net'] - 64 * MiB
    print(f"INFO mmap same-N-dependence test: mmap net {mm/MiB:.1f} ≥ compressed-6 net − 64 = {(R['6']['net']-64*MiB)/MiB:.1f}? {mm_invalid}")
row1 = ok_flat and ok_wait and ok_over and ok_pair and bool(mm_ok) and len(comp) == 4
if mm_invalid: m = 'B3g row 5: mmap control shows the same N-dependence — measurement invalid'
elif over: m = 'B3g row 2: direct memory above the ceiling — claim wrong (overshoot)'
elif row1 and ok_band: m = 'B3g row 1: plateaus step by ≈ ΔN×64 MiB, flat, waits grow — claim supported (Confirmed)'
elif row1: m = 'B3g row 1 matched but a B3f absolute band missed (Partial)'
elif nochange and ok_wait: m = 'B3g row 3: plateau does not change with N while waits grow — claim not supported'
elif notreached: m = f'B3g row 4: limit not reached for N={notreached} — not confirmed'
else: m = 'Not confirmed (no matching row)'
print('MATCHED:', m); print('FAILS:', fails)
