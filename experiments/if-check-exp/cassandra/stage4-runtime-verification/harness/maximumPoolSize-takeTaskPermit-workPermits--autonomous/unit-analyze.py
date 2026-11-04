#!/usr/bin/env python3
"""B2f/B2g checks (with R2/R4) as EXPECTED lines. usage: unit-analyze.py <unit log dir>  (reads rep1..3.probe)"""
import re, sys, os
d = sys.argv[1]
def recs(rep):
    out = []
    p = os.path.join(d, rep + '.probe')
    if not os.path.exists(p):
        return out
    for l in open(p):
        kv = dict(re.findall(r'(\w+)=([-\w.]+)', l))
        out.append(kv)
    return out
yes = no = 0
def expect(desc, c):
    global yes, no
    if c: yes += 1
    else: no += 1
    print(f'EXPECTED: {desc} — {"yes" if c else "NO"}')
def f(r, k): return float(r[k])
def i(r, k): return int(r[k])
M = 2000
p1all = {}
for rep in ('rep1', 'rep2', 'rep3'):
    R = recs(rep)
    if not R:
        expect(f'{rep}: PROBE lines present', False); continue
    get = lambda ph, **kw: [r for r in R if r.get('phase') == ph and all(r.get(k) == str(v) for k, v in kw.items())]
    p1 = {int(r['max']): r for r in get('1')}
    expect(f'{rep}: phase 1 has n = 1,4,32,128 (got {sorted(p1)})', sorted(p1) == [1, 4, 32, 128])
    for n, r in sorted(p1.items()):
        expect(f'{rep} P1 n={n}: active={r["active"]} running={r["running"]} peak={r["peak"]} = n; pending={r["pending"]} = {M-n}',
               i(r,'active') == n and i(r,'running') == n and i(r,'peak') == n and i(r,'pending') == M - n)
        expect(f'{rep} P1 n={n}: heapDelta {r["heapDeltaMiB"]} MiB in 110–145', 110 <= f(r,'heapDeltaMiB') <= 145)
    if p1:
        hs = [f(r,'heapDeltaMiB') for r in p1.values()]; mean = sum(hs) / len(hs)
        expect(f'{rep} P1: heapDelta the same across n within ±10 MiB (mean {mean:.1f}, range {min(hs):.1f}–{max(hs):.1f})', all(abs(h - mean) <= 10 for h in hs))
        if 1 in p1 and 128 in p1:
            expect(f'{rep} P1: NOT "falls ∝ n" (R2: heapDelta(1) < heapDelta(128) − 20): {f(p1[1],"heapDeltaMiB")} vs {f(p1[128],"heapDeltaMiB")}',
                   not (f(p1[1],'heapDeltaMiB') < f(p1[128],'heapDeltaMiB') - 20))
        p1all[rep] = {n: f(r,'heapDeltaMiB') for n, r in p1.items()}
    a, b, c = get('2a'), get('2b'), get('2c')
    if a and b and c:
        a, b, c = a[0], b[0], c[0]
        expect(f'{rep} P2a: max 32 active {a["active"]} pending {a["pending"]} running {a["running"]} = 32/200/32; heap {a["heapDeltaMiB"]} in 13–20',
               i(a,'max') == 32 and i(a,'active') == 32 and i(a,'pending') == 200 and i(a,'running') == 32 and 13 <= f(a,'heapDeltaMiB') <= 20)
        expect(f'{rep} P2b: max {b["max"]} = 4, active {b["active"]} = 32 (> max: workPermits = −28), pending {b["pending"]} = 200',
               i(b,'max') == 4 and i(b,'active') == 32 and i(b,'pending') == 200)
        expect(f'{rep} P2c (line 165 exits): active {c["active"]} = 4, running {c["running"]} = 4, pending {c["pending"]} = 196; heap {c["heapDeltaMiB"]} in 11–18',
               i(c,'active') == 4 and i(c,'running') == 4 and i(c,'pending') == 196 and 11 <= f(c,'heapDeltaMiB') <= 18)
    else:
        expect(f'{rep}: phase 2 lines present', False)
    p3 = {int(r['limitMiB']): r for r in get('3')}
    for lim, acc, lo, hi in ((16, 256, 14, 22), (64, 1024, 58, 75)):
        r = p3.get(lim)
        expect(f'{rep} P3 cap {lim} MiB: accepted {r and r["accepted"]} = {acc}, heap {r and r["heapDeltaMiB"]} in {lo}–{hi}',
               r is not None and i(r,'accepted') == acc and lo <= f(r,'heapDeltaMiB') <= hi)
    p4 = {int(r['max']): r for r in get('4')}
    for n, lo, hi in ((1, 1, 3), (4, 4, 6), (32, 32, 35), (128, 128, 135)):
        r = p4.get(n)
        expect(f'{rep} P4 (R4) n={n}: active/running/peak {r and (r["active"], r["running"], r["peak"])} = n, pending {r and r["pending"]} = {M-n}, heap {r and r["heapDeltaMiB"]} in {lo}–{hi}',
               r is not None and i(r,'active') == n and i(r,'running') == n and i(r,'peak') == n and i(r,'pending') == M - n and lo <= f(r,'heapDeltaMiB') <= hi)
    info = get('4info')
    print(f'INFO {rep}: test JVM max heap {info[0]["xmxMiB"] if info else "?"} MiB')
if len(p1all) == 3:
    worst = max(abs(p1all[x][n] - p1all[y][n]) for n in (1, 4, 32, 128) for x in p1all for y in p1all if n in p1all[x] and n in p1all[y])
    expect(f'R2 repeat row: Phase 1 heapDelta across the three reps differ ≤ 10 MiB (worst {worst:.1f})', worst <= 10)
print(f'EXPECTED tally: {yes} yes, {no} NO')
