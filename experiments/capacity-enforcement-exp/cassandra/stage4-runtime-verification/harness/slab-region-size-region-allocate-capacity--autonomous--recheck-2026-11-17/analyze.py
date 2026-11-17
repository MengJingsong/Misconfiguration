#!/usr/bin/env python3
"""Analysis of the recheck stage-4 run (design section of 2026-11-17 in the case file, frozen hash cd3c3273...).
usage: analyze.py <logs dir holding H2048/ U2048/ H256/ H64/>   prints the readings, P1-P7, validity and the matched row.
Rules (from the design): R(N) = [B bytes at sN minus at c1; A(N) = global AllMemtablesOnHeapDataSize at sN minus at c1;
slopes = least squares over N = 0 (c1), 50, 100, 200, 400; Rc, Ac = c1 minus s0. Literals typed from the frozen section."""
import json, os, re, sys

MIB, KIB = 1 << 20, 1 << 10
D = sys.argv[1]
ARMS = ['H2048', 'U2048', 'H256', 'H64']
HEAP = ['H2048', 'H256', 'H64']


def slope(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


def ok(b):
    return 'ok' if b else 'MISS'


res, lines = {}, []
P = lambda s: lines.append(s)
for a in ARMS:
    f = f'{D}/{a}/steps.json'
    if not os.path.exists(f):
        P(f'{a}: steps.json missing'); continue
    j = json.load(open(f))
    st = {s['step']: s for s in j['steps']}
    c1 = st['c1']
    Ns = [0, 50, 100, 200, 400]
    keys = ['c1', 's50', 's100', 's200', 's400']
    R = [st[k]['bb'] - c1['bb'] for k in keys]
    A = [st[k]['on'] - c1['on'] for k in keys]
    T = [st[k]['hist_total'] - c1['hist_total'] for k in keys]
    r = {'slope_R': slope(Ns, R), 'slope_A': slope(Ns, A), 'slope_T': slope(Ns, T), 'R': dict(zip(Ns, R)), 'A': dict(zip(Ns, A)),
         'Rc': c1['bb'] - st['s0']['bb'], 'Ac': c1['on'] - st['s0']['on'], 'st': st, 'j': j,
         'bn': {k: st[k]['bn'] - c1['bn'] for k in keys}}
    res[a] = r
    P(f'== {a} ({j["alloc"]}, memtable_heap_space read back {j["settings"].get("memtable_heap_space")}, heap {j["xmx"]})')
    P('  step   [B bytes        [B n     hist total      heap used      gauge on    tables>0  flush(ks) cg.current')
    for k in ['s0'] + keys + (['pc'] if 'pc' in st else []):
        s = st[k]
        P(f'  {k:5} {s["bb"]:>13,} {s["bn"]:>9,} {s["hist_total"]:>15,} {s["heap_used"]:>14,} {s["on"]:>11,} {s["tables_with_data"]:>9} {s["flush_lines"]:>9} {s["cg_current"]}')
    P('  N: R(N) MiB / A(N) KiB / R per table MiB / [B instances delta: ' + '; '.join(
        f'{n}: {R[i]/MIB:.2f} / {A[i]/KIB:.1f} / {(R[i]/n/MIB if n else 0):.4f} / {r["bn"][keys[i]]}' for i, n in enumerate(Ns)))
    P(f'  slope_R {r["slope_R"]/MIB:.4f} MiB/table ({r["slope_R"]:.0f} B); slope_A {r["slope_A"]/KIB:.3f} KiB/table; '
      f'slope of histogram total {r["slope_T"]/MIB:.4f} MiB/table; Rc {r["Rc"]/MIB:.3f} MiB; Ac {r["Ac"]/MIB:.3f} MiB; '
      f'first-vs-second histogram [B differences: ' + ', '.join(f'{(st[k]["bb_first"]-st[k]["bb"])/KIB:.0f} KiB' for k in ['s0'] + keys))

checks = {}
P('')
P('== Predictions (frozen literals)')
for a in HEAP:
    if a not in res: continue
    r = res[a]
    p1 = 0.95 * MIB <= r['slope_R'] <= 1.10 * MIB and 190 * MIB <= r['R'][200] <= 225 * MIB and 380 * MIB <= r['R'][400] <= 445 * MIB
    p2 = 1.0 * KIB <= r['slope_A'] <= 3.0 * KIB and 0.2 * MIB <= r['A'][200] <= 0.6 * MIB and r['A'][200] > 0 and r['R'][200] / r['A'][200] >= 300
    p6 = 0.9 * MIB <= r['Rc'] <= 2.5 * MIB and 0.4 * MIB <= r['Ac'] <= 1.2 * MIB
    checks[a] = {'P1': p1, 'P2': p2, 'P6': p6}
    P(f'  {a}: P1 slope_R in [0.95,1.10] MiB, R(200) in [190,225] MiB, R(400) in [380,445] MiB: {ok(p1)} '
      f'({r["slope_R"]/MIB:.4f}, {r["R"][200]/MIB:.2f}, {r["R"][400]/MIB:.2f})')
    P(f'  {a}: P2 slope_A in [1,3] KiB, A(200) in [0.2,0.6] MiB, R/A(200) >= 300: {ok(p2)} '
      f'({r["slope_A"]/KIB:.3f}, {r["A"][200]/MIB:.3f}, {r["R"][200]/max(r["A"][200],1):.0f})')
    P(f'  {a}: P6 Rc in [0.9,2.5] MiB, Ac in [0.4,1.2] MiB: {ok(p6)} ({r["Rc"]/MIB:.3f}, {r["Ac"]/MIB:.3f})')
hs = [res[a]['slope_R'] for a in HEAP if a in res]
p3 = len(hs) == 3 and max(hs) / min(hs) <= 1.05
checks['P3'] = p3
P(f'  P3 heap_buffers slopes max/min <= 1.05: {ok(p3)} ({max(hs)/min(hs):.4f})' if hs else '  P3: no data')
if 'H64' in res:
    st = res['H64']['st']
    p4 = res['H64']['R'][400] > 64 * MIB and st['s400']['on'] < 0.02 * 64 * MIB and st['s400']['flush_lines'] == 0
    checks['P4'] = p4
    P(f'  P4 H64 R(400) > 64 MiB, gauge at s400 < 1.28 MiB, no ks flush line before pc: {ok(p4)} '
      f'(R(400) {res["H64"]["R"][400]/MIB:.2f} MiB = {res["H64"]["R"][400]/(64*MIB):.2f} L; gauge {st["s400"]["on"]/MIB:.3f} MiB; flush lines {st["s400"]["flush_lines"]})')
    pc = st.get('pc')
    if pc:
        dpc = pc['bb'] - st['s400']['bb']
        p7_core = pc['flush_t0_limit'] >= 1 and pc['on'] <= 0.40 * 64 * MIB
        p7 = p7_core and pc['flush_lines_small'] == 0 and pc['small_with_data'] == 400 and -2 * MIB <= dpc <= 30 * MIB
        checks['P7'], checks['P7core'] = p7, p7_core
        P(f'  P7 H64 positive control: t0 MEMTABLE_LIMIT flushes {pc["flush_t0_limit"]} (>=1), small-table flush lines {pc["flush_lines_small"]} (0), '
          f'small tables with data {pc["small_with_data"]} (400), gauge after pc {pc["on"]/MIB:.3f} MiB (<= 25.6), [B pc - s400 {dpc/MIB:.2f} MiB ([-2,30]): {ok(p7)}')
if 'U2048' in res:
    r = res['U2048']
    p5 = r['slope_R'] <= 16 * KIB and 1.0 * KIB <= r['slope_A'] <= 3.0 * KIB
    p6u = 0.2 * MIB <= r['Rc'] <= 1.5 * MIB
    checks['P5'], checks['P6U'] = p5, p6u
    P(f'  P5 U2048 slope_R <= 16 KiB, slope_A in [1,3] KiB: {ok(p5)} ({r["slope_R"]/KIB:.3f} KiB, {r["slope_A"]/KIB:.3f} KiB)')
    P(f'  P6 U2048 Rc in [0.2,1.5] MiB: {ok(p6u)} ({r["Rc"]/MIB:.3f} MiB)')

P('')
P('== Validity')
valid = True
for a in ARMS:
    if a not in res:
        valid = False; continue
    j, st = res[a]['j'], res[a]['st']
    summ = open(f'{D}/{a}/summary.txt').read()
    exp_no = [l for l in summ.splitlines() if l.startswith('EXPECTED') and not re.search(r': yes(;|$)', l.rstrip())]  # the JVM-flags line continues after 'yes'
    tables_ok = all(st[k]['tables_with_data'] == n + 1 for k, n in [('c1', 0), ('s50', 50), ('s100', 100), ('s200', 200), ('s400', 400)])
    noflush = all(st[k]['flush_lines'] == 0 for k in ['s0', 'c1', 's50', 's100', 's200', 's400'])
    cl_ok = all((st[k].get('client') or {}).get('err', 1) == 0 for k in ['c1', 's50', 's100', 's200', 's400'] + (['pc'] if 'pc' in st else []))
    errs = re.search(r'ERROR lines in system.log: (\d+)', summ)
    oom = re.search(r'oom_kill (\d+)', summ)
    v = not exp_no and tables_ok and noflush and cl_ok and errs and errs.group(1) == '0' and (not oom or oom.group(1) == '0')
    valid = valid and bool(v)
    P(f'  {a}: EXPECTED lines all yes: {ok(not exp_no)}; tables with data = N+1 at every step: {ok(tables_ok)}; no ks flush before pc: {ok(noflush)}; '
      f'client errors 0: {ok(cl_ok)}; ERROR lines {errs.group(1) if errs else "?"}; oom_kill {oom.group(1) if oom else "?"} -> {ok(v)}')

P('')
heapA = [a for a in HEAP if a in res]
sR = {a: res[a]['slope_R'] for a in heapA}
sA = {a: res[a]['slope_A'] for a in heapA}
if not valid:
    row = 'Invalid'
elif any(v <= 0.10 * MIB for v in sR.values()):
    row = 'Refuted: no region retained per table'
elif any(v >= 0.5 * MIB for v in sA.values()):
    row = 'Refuted: the regions are charged'
elif 'H64' in res and res['H64']['st'].get('pc', {}).get('flush_lines_small', 0) > 0 and res['H64']['R'][400] <= 64 * MIB:
    row = 'Refuted: the pool limit caps the region bytes'
elif 'U2048' in res and res['U2048']['slope_R'] >= 0.5 * sR.get('H2048', 0):
    row = 'Not confirmed: mechanism not isolated'
elif all(checks.get(a, {}).get(p) for a in HEAP for p in ('P1', 'P2', 'P6')) and checks.get('P3') and checks.get('P5') and checks.get('P6U') \
        and checks.get('P4') and checks.get('P7core'):
    row = 'Confirmed - does not cap'
elif any(0.10 * MIB < v < 0.95 * MIB or v > 1.10 * MIB for v in sR.values()) and all(checks.get(a, {}).get('P2') for a in HEAP):
    row = 'Not confirmed: real exceeds counted, but not by one region per table'
elif not checks.get('P3') and any(checks.get(a, {}).get('P1') for a in HEAP):
    row = 'Not confirmed: real follows the limit knob in part'
elif not checks.get('P7core'):
    row = 'Not confirmed: positive control did not bind'
else:
    row = 'Not confirmed (no matching row)'
P(f'MATCHED ROW: {row}')
P('P7 full (secondary parts included): ' + ok(checks.get('P7')))
print('\n'.join(lines))
