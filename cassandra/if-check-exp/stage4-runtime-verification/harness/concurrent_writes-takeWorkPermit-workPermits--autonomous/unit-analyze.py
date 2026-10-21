#!/usr/bin/env python3
"""unit-analyze.py <unit log dir>: B2f / B2g checks of concurrent_writes-takeWorkPermit-workPermits--autonomous (with
audit amendment R6) on the PROBE lines of rep1.probe, rep2.probe (M = 4000) and m8000.probe (M = 8000). Prints one
'EXPECTED: <check> — yes|NO' line per check and a tally. A NO is recorded, not fatal; the AI judges it in the results."""
import re, sys

L = sys.argv[1]
S = 64 * 1024
MIB = 1 << 20
res = {'yes': 0, 'no': 0}


def ex(desc, cond):
    res['yes' if cond else 'no'] += 1
    print(f'EXPECTED: {desc} — {"yes" if cond else "NO"}')


def load(rep):
    rows = []
    for l in open(f'{L}/{rep}.probe'):
        if not l.startswith('PROBE'):
            continue
        d = dict(kv.split('=', 1) for kv in l.split()[1:])
        rows.append({k: (v if k == 'mei_inline' else float(v)) for k, v in d.items()})
    return rows


reps = {r: load(r) for r in ('rep1', 'rep2', 'm8000')}
M_OF = {'rep1': 4000, 'rep2': 4000, 'm8000': 8000}
claim = {}
for rep, rows in reps.items():
    M = M_OF[rep]
    cl = [r for r in rows if r['cap'] == 0]
    pc = [r for r in rows if r['cap'] > 0]
    ex(f'{rep}: 4 claim rows (N 0, 2, 32, 128) and 4 control rows', [int(r['n']) for r in cl] == [0, 2, 32, 128] and len(pc) == 4)
    claim[rep] = {int(r['n']): r for r in cl}
    pay = M * S / MIB
    for r in cl:
        n = int(r['n'])
        ex(f'{rep} N={n}: active = min(N, M) = {min(n, M)} (read {r["active"]:.0f})', r['active'] == min(n, M))
        ex(f'{rep} N={n}: maxPool read back = N (read {r["maxPool"]:.0f})', r['maxPool'] == n)
        ex(f'{rep} N={n}: pending = M - N + 1 = {M - n + 1} (read {r["pending"]:.0f})', r['pending'] == M - n + 1)
        ex(f'{rep} N={n}: line 196 refuses the caller-runs path: mei_inline=false, pendingDelta 1 (read {r["mei_inline"]}, {r["mei_pendingDelta"]:.0f})',
           r['mei_inline'] == 'false' and r['mei_pendingDelta'] == 1)
        ex(f'{rep} N={n}: payloadMiB = {pay:.1f} (read {r["payloadMiB"]})', abs(r['payloadMiB'] - pay) < 0.05)
        ex(f'{rep} N={n}: liveDelta {r["liveDeltaMiB"]} MiB within ±10 % of {pay:.0f} MiB', abs(r['liveDeltaMiB'] - pay) <= 0.10 * pay)
    lv = {int(r['n']): r['liveDeltaMiB'] for r in cl}
    if len(lv) == 4:
        ratio = max(lv.values()) / min(lv.values())
        ex(f'{rep}: claim liveDelta varies by at most 10 % across N (max/min {ratio:.3f})', ratio <= 1.10)
        grows = lv[128] > 1.10 * min(lv[0], lv[2]) and lv[128] == max(lv.values())
        ex(f'{rep}: liveDelta does NOT grow with N (R6 definition; 128: {lv[128]}, 0: {lv[0]}, 2: {lv[2]})', not grows)
        falls = lv[0] < lv[128] / 1.10 and lv[0] == min(lv.values())
        ex(f'{rep}: no downward trend as N falls (N=0 not > 10 % below N=128)', not falls)
    for r in pc:
        cap, n = int(r['cap']), int(r['n'])
        exp_sub = cap // S
        ex(f'{rep} control cap={cap >> 20} MiB N={n}: submitted {exp_sub}, rejected {M - exp_sub} (read {r["submitted"]:.0f}, {r["rejected"]:.0f})',
           r['submitted'] == exp_sub and r['rejected'] == M - exp_sub)
        tol = 4 if cap == 16 * MIB else 8
        ex(f'{rep} control cap={cap >> 20} MiB N={n}: liveDelta {r["liveDeltaMiB"]} within {cap >> 20} ± {tol} MiB',
           abs(r['liveDeltaMiB'] - (cap >> 20)) <= tol)
        ex(f'{rep} control cap={cap >> 20} MiB N={n}: active = min(N, submitted) (read {r["active"]:.0f})', r['active'] == min(n, exp_sub))
    c16 = [r['liveDeltaMiB'] for r in pc if r['cap'] == 16 * MIB]
    c64 = [r['liveDeltaMiB'] for r in pc if r['cap'] == 64 * MIB]
    if c16 and c64:
        ex(f'{rep}: control follows the cap (64 MiB rows {c64} > 16 MiB rows {c16}, ratio {min(c64) / max(c16):.2f})', min(c64) > 2 * max(c16))
    for l in open(f'{L}/{rep}.probe'):
        if l.startswith('SUPPL'):
            d = dict(kv.split('=', 1) for kv in l.split()[2:])
            ex(f'{rep} SUPPLEMENTARY idle executor k={d["k"]}: maybeExecuteImmediately ran on a worker, not inline (line 196 also needs a queued task; ran={d["ran"]}, inline={d["mei_inline"]})',
               d['ran'] == 'true' and d['mei_inline'] == 'false')

if all(len(claim[r]) == 4 for r in claim):
    for n in (0, 2, 32, 128):
        a, b = claim['rep1'][n]['liveDeltaMiB'], claim['rep2'][n]['liveDeltaMiB']
        ex(f'repeat N={n}: rep1 {a} vs rep2 {b} MiB within 10 % (B2h, R6)', abs(a - b) <= 0.10 * min(a, b))
        q = claim['m8000'][n]['liveDeltaMiB'] / ((a + b) / 2)
        ex(f'M 4000 -> 8000 N={n}: liveDelta ratio {q:.3f} in [1.8, 2.2] (B2g row 5, R6)', 1.8 <= q <= 2.2)
print(f'unit-analyze: {res["yes"]} yes, {res["no"]} NO')
