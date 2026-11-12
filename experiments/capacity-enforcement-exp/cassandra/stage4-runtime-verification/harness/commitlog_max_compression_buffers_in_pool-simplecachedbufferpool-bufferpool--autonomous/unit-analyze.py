#!/usr/bin/env python3
"""Unit-tier analyzer (B2f/B2g as amended M2-M4). usage: unit-analyze.py <outdir>.
Thresholds fixed 2026-11-11 before any reading. Prints every check as PASS/FAIL and the matched B2g row."""
import re, sys
OUT = sys.argv[1]
MiB = 1 << 20
def kv(line):
    return dict(re.findall(r'(\w+)=(\[[^\]]*\]|\S+)', line))
res = {}; fails = 0
def check(name, ok, detail):
    global fails
    print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")
    if not ok: fails += 1
    return ok
row1_all = True; overshoot = False; notreached = False; memgap = False; nomatch = False
for n in (3, 5, 8):
    # the TEST-<class>.log is appended across ant runs: keep only this N's lines (fix 2026-11-11, harness fault D1)
    L = [l for l in open(f'{OUT}/test-PoolCapManagerTest-{n}.log') if 'O44 ' in l and f'CAP_N={n} ' in l]
    base = kv(next(l for l in L if 'O44 BASE' in l))
    s5 = kv(next(l for l in L if 'O44 SAMPLE' in l and 't=5s' in l))
    s3 = kv(next(l for l in L if 'O44 SAMPLE' in l and 't=3s' in l))
    af = kv(next(l for l in L if 'O44 AFTER' in l))
    u0 = int(base['u0']); act = int(s5['active']); used = int(s5['used']); dd = int(s5['directDelta'])
    exp = (n - u0) * MiB; tol = max(0.10 * exp, 256 * 1024)
    c = [check(f'N={n} active=N', act == n, f'active={act} (3s: {s3["active"]})'),
         check(f'N={n} usedBuffers=N', used == n, f'used={used}'),
         check(f'N={n} directDelta=(N-u0) MiB', abs(dd - exp) <= tol, f'u0={u0} directDelta={dd} expected={exp} tol={int(tol)}'),
         check(f'N={n} atLimit', s5['atLimit'] == 'true', s5['atLimit']),
         check(f'N={n} writer alive and in awaitAvailableSegment', s5['alive'] == 'true' and s5['writerInAwait'] == 'true', f"alive={s5['alive']} inAwait={s5['writerInAwait']} top={s5['writerTop']}"),
         check(f'N={n} waitsAfter>=1', int(af['waitsAfter']) >= 1, f"waits@5s={s5['waits']} waitsAfter={af['waitsAfter']} writerDone={af['writerDone']}")]
    print(f"INFO N={n} 3s→5s active {s3['active']}→{s5['active']} used {s3['used']}→{s5['used']} direct {s3['directDelta']}→{s5['directDelta']}")
    if not all(c): row1_all = False
    if act > n or used > n: overshoot = True
    if act < n and af['writerDone'] == 'true' and s5['alive'] == 'false': notreached = True
    if act == n and dd > exp + max(0.5 * exp, 2 * MiB): memgap = True
    if s5['alive'] == 'true' and act < n and s5['writerInAwait'] == 'false': nomatch = True
    res[n] = (act, used, dd)
# class 2
pred_ret = {3: 4, 5: 8, 8: 8}; c2ok = True; c2_retN = 0; c2_caps = False
for n in (3, 5, 8):
    L = [l for l in open(f'{OUT}/test-PoolQueueCapacityTest-{n}.log') if 'O44 Q' in l and f'CAP_N={n} ' in l]
    ac = kv(next(l for l in L if 'afterCreate' in l)); rr = kv(next(l for l in L if 'retained=' in l)); n1 = kv(next(l for l in L if 'N1=' in l))
    used = int(re.search(r'usedBuffers:(\d+)', ac['pool']).group(1)); dd = int(ac['directDelta']); ret = int(rr['retained'])
    a = check(f'C2 N={n} usedBuffers=10', used == 10, f'used={used}')
    b = check(f'C2 N={n} directDelta≈10 MiB (±10%)', abs(dd - 10 * MiB) <= MiB, f'directDelta={dd}')
    d = check(f'C2 N={n} atLimit', ac['atLimit'] == 'true', ac['atLimit'])
    e = check(f'C2 N={n} retained={pred_ret[n]}', ret == pred_ret[n], f'retained={ret}')
    f = check(f'C2 N={n} N=1 throws IllegalArgumentException', n1['N1'] == 'java.lang.IllegalArgumentException', n1['N1'])
    if used < 10: c2_caps = True
    if ret == n: c2_retN += 1
    c2ok = c2ok and a and b and d
tracks = res[3][0] < res[5][0] < res[8][0]
check('plateau tracks N (3<5<8)', tracks, str({k: v[0] for k, v in res.items()}))
print('C2 rows: retained = N exactly in', c2_retN, 'of 3 values (row "queue not rounded" if 3 of 3 for N=3,5)', '; pool caps by itself:', c2_caps)
if overshoot: row = 'B2g row 2: active or usedBuffers > N — claim wrong (overshoot)'
elif row1_all and tracks and c2ok: row = 'B2g row 1: active = usedBuffers = N, direct ≈ (N-u0) MiB, writer blocked, waits ≥ 1 — claim supported'
elif memgap: row = 'B2g row 4: active = N but direct ≫ — claim partly wrong'
elif notreached: row = 'B2g row 3: limit not reached — not confirmed'
else: row = 'Not confirmed (no matching row)'
print('MATCHED:', row); print('FAILS:', fails)
