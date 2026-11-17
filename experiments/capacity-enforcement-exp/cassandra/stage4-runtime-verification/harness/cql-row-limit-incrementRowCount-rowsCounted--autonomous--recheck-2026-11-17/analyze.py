#!/usr/bin/env python3
"""Analyzer of the recheck run: design S6 (R1-R5, model bands) and S7 (conclusions row). Not upstream code.
  analyze.py <logs-dir>     reads <logs>/U/{queries.jsonl,alloc.csv,session.log} and <logs>/C/...; prints the summary.
Only queries tagged 'run' (3 repetitions per arm) are readings; 'warm', 'trigger' and 'check' are not."""
import sys, os, json, statistics as st, bisect, re
LOGS = sys.argv[1]
MiB = 2 ** 20
W = {'w16k': 16384, 'w128k': 131072, 'w1m': 1048576}
def load(life):
    p = os.path.join(LOGS, life, 'queries.jsonl')
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []
def samples(life):
    p = os.path.join(LOGS, life, 'alloc.csv'); S = []
    if not os.path.exists(p): return S
    for l in open(p):
        w = l.strip().split(',')
        if len(w) == 3 and w[0].isdigit(): S.append((int(w[0]), int(w[1])))
    return S
def interp(S, t):
    ts = [s[0] for s in S]; i = bisect.bisect_left(ts, t)
    if i <= 0 or i >= len(S): return None
    (t0, a0), (t1, a1) = S[i - 1], S[i]
    return a0 + (a1 - a0) * (t - t0) / max(1, t1 - t0)
def alloc(S, q):
    t0, t1 = q['t0_ms'], q['t1_ms'] + 1000; i0 = q['B']['t1'] + 200
    a = [interp(S, x) for x in (i0, t0, t1)]
    if None in a or t0 - i0 < 500: return None
    rate = (a[1] - a[0]) / (t0 - i0)
    return (a[2] - a[1]) - rate * (t1 - t0)
def held(q, kind):
    prs = [p for p in q['probes'] if p['kind'] == kind]
    if not prs or prs[0]['hist']['total'] is None: return None, False
    return prs[0]['hist']['total'] - q['B']['total'], prs[0]['inside']
def med(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None
def nw(arm_q):
    n = 600 if arm_q['N'] == 'none' else int(arm_q['N'])
    return n, n * W[arm_q['table']]
def fmt(x, d=MiB, u='MiB'):
    return 'n/a' if x is None else '%.1f %s' % (x / d, u)

out = []
def P(*a): out.append(' '.join(str(x) for x in a))
EXP = []
def E(name, ok, detail):
    EXP.append((name, ok)); P('EXPECTED %-58s %s  (%s)' % (name, 'ok' if ok else 'MISMATCH', detail))

res = {}
for life in ('U', 'C'):
    Q = [q for q in load(life) if q['tag'] == 'run']
    S = samples(life)
    arms = {}
    for q in Q:
        q['A'] = alloc(S, q) if S else None
        for k in ('PR', 'PC', 'PA'):
            q['H' + k[1]], q['in' + k[1]] = held(q, k)
        arms.setdefault(q['arm'], []).append(q)
    res[life] = arms
    P('== lifetime %s: %d run queries, %d arms, %d alloc samples' % (life, len(Q), len(arms), len(S)))
    noise = [q['B2']['total'] - q['B']['total'] for q in Q if q['B2']['total'] is not None and q['B']['total'] is not None]
    if noise: P('   B2 - B: median %+.2f MiB, min %+.2f, max %+.2f' % (st.median(noise) / MiB, min(noise) / MiB, max(noise) / MiB))
    res[life + '_noise'] = st.median(noise) if noise else None
    for a in sorted(arms, key=lambda a: (arms[a][0]['table'], str(arms[a][0]['N']).zfill(5), arms[a][0]['kind'])):
        qs = sorted(arms[a], key=lambda q: q['rep']); n, NW = nw(qs[0])
        hr, hc, ha = med([q['HR'] for q in qs if q['inR']]), med([q['HC'] for q in qs if q['inC']]), med([q['HA'] for q in qs if q['inA']])
        A = med([q['A'] for q in qs])
        caps = [int(re.search(r'cap=(\d+)', p['info']).group(1)) for q in qs for p in q['probes'] if p['kind'] == 'PR' and 'cap=' in p['info']]
        sizes = [int(re.search(r'size=(\d+)', p['info']).group(1)) for q in qs for p in q['probes'] if p['kind'] == 'PR' and 'size=' in p['info']]
        P('ARM %s %-12s N=%-4s W=%-7d NxW=%7.1f MiB | rows %s | err %s | H_R %s (%.2f NxW) | H_C %s (%.2f NxW) | H_C-H_R %s | H_A %s | A %s (%s NxW) | cap %s size %s | inside R/C/A %s/%s/%s | reps %s' % (
            life, a, qs[0]['N'], W[qs[0]['table']], NW / MiB, [q['rows'] for q in qs], sum(1 for q in qs if q['err']),
            fmt(hr), (hr or 0) / NW, fmt(hc), (hc or 0) / NW, fmt(None if hr is None or hc is None else hc - hr), fmt(ha),
            fmt(A), 'n/a' if A is None else '%.2f' % (A / NW), fmt(med(caps)), fmt(med(sizes)),
            sum(1 for q in qs if q['inR']), sum(1 for q in qs if q['inC']), sum(1 for q in qs if q['inA']), len(qs)))
        res[(life, a)] = dict(n=n, NW=NW, hr=hr, hc=hc, ha=ha, A=A, cap=med(caps), size=med(sizes), qs=qs)
        for q in qs:
            P('    rep %s rows %s err %s | B %.1f MiB B2-B %+.1f | %s | A %s' % (q['rep'], q['rows'], (q['err'] or '-')[:120], q['B']['total'] / MiB, (q['B2']['total'] - q['B']['total']) / MiB,
              ' '.join('%s %s inside=%s [%s]' % (p['kind'], fmt(p['hist']['total'] - q['B']['total']), p['inside'], p['info'][:70]) for p in q['probes']), fmt(q['A'])))

U, C = res['U'], res['C']
def g(life, a): return res.get((life, a))
LARGE = ['L512-w16k', 'L32-w128k', 'L128-w128k', 'L512-w128k', 'L32-w1m', 'L128-w1m', 'L512-w1m', 'Lnone-w128k', 'P128-w1m', 'P512-w1m']
P('')
P('== Predictions (design S6) ==')
# R1
r1 = []
for a, qs in U.items():
    for q in qs:
        n = 600 if q['N'] == 'none' else int(q['N'])
        pcrows = [int(re.search(r'rows=(\d+)', p['info']).group(1)) for p in q['probes'] if p['kind'] == 'PC']
        r1.append(not q['err'] and q['rows'] == n and pcrows == [n])
R1 = bool(r1) and all(r1); E('R1 every U query returns N rows; PC logs N rows', R1, '%d of %d queries' % (sum(r1), len(r1)))
# R2
r2 = []
for a in LARGE:
    x = g('U', a); ok = x is not None and x['hc'] is not None and x['hc'] >= 0.9 * x['NW']; r2.append(ok)
    E('R2 H_C >= 0.9 NxW  %s' % a, ok, 'H_C/NxW = %s' % ('n/a' if not x or x['hc'] is None else '%.2f' % (x['hc'] / x['NW'])))
for n in (128, 512):
    a, b = g('U', 'L%d-w16k' % n), g('U', 'L%d-w1m' % n)
    k = None if not a or not b or a['hc'] is None or b['hc'] is None else (b['hc'] - a['hc']) / (n * (W['w1m'] - W['w16k']))
    ok = k is not None and k >= 0.9; r2.append(ok); E('R2 width slope at N=%d >= 0.9' % n, ok, 'k = %s' % ('n/a' if k is None else '%.3f' % k))
for t in ('w128k', 'w1m'):
    a, b = g('U', 'L32-%s' % t), g('U', 'L512-%s' % t)
    k = None if not a or not b or a['hc'] is None or b['hc'] is None else (b['hc'] - a['hc']) / (480 * W[t])
    ok = k is not None and k >= 0.9; r2.append(ok); E('R2 count slope at W=%s >= 0.9' % t, ok, 'k = %s' % ('n/a' if k is None else '%.3f' % k))
R2 = all(r2)
# R3
r3 = []
for a in LARGE:
    x = g('U', a)
    ok = x is not None and None not in (x['hr'], x['hc']) and x['hr'] >= 0.9 * x['NW'] and (x['hc'] - x['hr']) >= 0.8 * x['NW']; r3.append(ok)
    E('R3 H_R >= 0.9 NxW and H_C-H_R >= 0.8 NxW  %s' % a, ok, 'H_R/NxW %s, (H_C-H_R)/NxW %s' % (
        'n/a' if not x or x['hr'] is None else '%.2f' % (x['hr'] / x['NW']), 'n/a' if not x or None in (x['hr'], x['hc']) else '%.2f' % ((x['hc'] - x['hr']) / x['NW'])))
R3 = all(r3)
# R4
r4 = []
for n in (128, 512):
    p, l = g('U', 'P%d-w1m' % n), g('U', 'L%d-w1m' % n)
    r = None if not p or not l or None in (p['hc'], l['hc']) else p['hc'] / l['hc']
    ok = r is not None and 0.67 <= r <= 1.5; r4.append(ok); E('R4 H_C page/limit at N=%d in [0.67, 1.5]' % n, ok, 'ratio %s' % ('n/a' if r is None else '%.3f' % r))
R4 = all(r4)
# R5
r5 = []
ABORT = ['L128-w1m', 'L512-w1m', 'L512-w128k', 'P128-w1m']; PASS = ['L32-w1m', 'L128-w128k', 'L512-w16k']
has = []
for a in ABORT:
    x = g('C', a)
    if not x: r5.append(False); E('R5 abort arm present %s' % a, False, 'missing'); continue
    qs = x['qs']
    ok = len(qs) == 3 and all(q['err'] and ('read' in q['err'].lower() or 'size' in q['err'].lower()) for q in qs) \
         and all(any(p['kind'] == 'PA' for p in q['probes']) and not any(p['kind'] == 'PC' for p in q['probes']) for q in qs)
    r5.append(ok); E('R5 %s fails 3/3 with read failure, PA fires, PC does not' % a, ok, '%s' % [(q['err'] or '-')[:60] for q in qs])
    ok2 = x['ha'] is not None and x['ha'] <= 100 * MiB; r5.append(ok2); has.append(x['ha'])
    E('R5 H_A <= 100 MiB  %s' % a, ok2, 'H_A %s, NxW %.0f MiB' % (fmt(x['ha']), x['NW'] / MiB))
hv = [h for h in has if h is not None]
ok = len(hv) == len(ABORT) and min(hv) > 0 and max(hv) / min(hv) <= 2.0; r5.append(ok)
E('R5 H_A max/min over abort arms <= 2', ok, 'max/min %s' % ('n/a' if not ok and (len(hv) < 2 or min(hv) <= 0) else '%.2f' % (max(hv) / min(hv))))
for a in PASS:
    x, u = g('C', a), g('U', a)
    r = None if not x or not u or None in (x['hc'], u['hc']) else x['hc'] / u['hc']
    rows_ok = bool(x) and all(not q['err'] and q['rows'] == x['n'] for q in x['qs'])
    ok = rows_ok and r is not None and 0.67 <= r <= 1.5; r5.append(ok)
    E('R5 pass arm %s returns N rows, H_C C/U in [0.67, 1.5]' % a, ok, 'C/U %s' % ('n/a' if r is None else '%.3f' % r))
R5 = all(r5)
P('')
P('== Model bands (recorded, not used for the row) ==')
for a in LARGE:
    x = g('U', a)
    if not x or None in (x['hr'], x['hc']): P('MODEL %s n/a' % a); continue
    b1 = x['cap'] and 0.95 <= x['hr'] / x['cap'] <= 1.15
    b2 = x['cap'] and x['size'] and 1.0 <= x['cap'] / x['size'] <= 2.0
    b3 = 0.95 <= (x['hc'] - x['hr']) / x['NW'] <= 1.3
    b4 = 2.0 <= x['hc'] / x['NW'] <= 3.5
    b5 = None if not a.endswith('w1m') or x['A'] is None else 2 <= x['A'] / x['NW'] <= 8
    P('MODEL %-12s H_R/cap %.3f %s | cap/size %.3f %s | (H_C-H_R)/NxW %.3f %s | H_C/NxW %.3f %s | A/NxW %s %s' % (
        a, x['hr'] / x['cap'] if x['cap'] else 0, 'hit' if b1 else 'MISS', x['cap'] / x['size'] if x['cap'] and x['size'] else 0, 'hit' if b2 else 'MISS',
        (x['hc'] - x['hr']) / x['NW'], 'hit' if b3 else 'MISS', x['hc'] / x['NW'], 'hit' if b4 else 'MISS',
        'n/a' if x['A'] is None else '%.2f' % (x['A'] / x['NW']), '' if b5 is None else ('hit' if b5 else 'MISS')))
for life in ('U', 'C'):
    nz = res.get(life + '_noise'); P('MODEL noise %s median B2-B %s (band +-4 MiB) %s' % (life, fmt(nz), 'n/a' if nz is None else ('hit' if abs(nz) <= 4 * MiB else 'MISS')))
# Refuted / invalid checks
a512, b512 = g('U', 'L512-w16k'), g('U', 'L512-w1m')
flat_ratio = None if not a512 or not b512 or None in (a512['hc'], b512['hc']) or a512['hc'] <= 0 else b512['hc'] / a512['hc']
low = [a for a in ('L128-w1m', 'L512-w1m') if g('U', a) and g('U', a)['hc'] is not None and g('U', a)['hc'] < 0.5 * g('U', a)['NW']]
REF = (flat_ratio is not None and flat_ratio < 4) or bool(low)
P('')
P('REFUTE-CHECK H_C(512,1MiB)/H_C(512,16KiB) = %s (refuted if < 4); arms with H_C < 0.5 NxW: %s' % ('n/a' if flat_ratio is None else '%.1f' % flat_ratio, low or 'none'))
inv = []
for life in ('U', 'C'):
    for a, qs in res[life].items():
        exp = ['PR', 'PC'] if (life == 'U' or a in PASS) else ['PA']
        for q in qs:
            kinds = [p['kind'] for p in q['probes']]
            for k in exp:
                if k not in kinds: inv.append('%s %s rep%s: probe %s missing' % (life, a, q['rep'], k))
        for k in exp:
            outside = sum(1 for q in qs for p in q['probes'] if p['kind'] == k and not p['inside'])
            if outside > 1: inv.append('%s %s: %d histograms of %s outside the pause' % (life, a, outside, k))
    nz = res.get(life + '_noise')
    if nz is not None and abs(nz) > 4 * MiB: inv.append('%s median B2-B %s' % (life, fmt(nz)))
    sl = os.path.join(LOGS, life, 'session.log')
    if os.path.exists(sl):
        t = open(sl).read()
        m = re.findall(r'java.lang.OutOfMemoryError lines: (\d+)', t)
        if m and int(m[-1]) > 0: inv.append('%s OutOfMemoryError lines %s' % (life, m[-1]))
        m = re.findall(r'oom_kill (\d+)', t)
        if m and int(m[-1]) > 0: inv.append('%s scope oom_kill %s' % (life, m[-1]))
P('INVALID-CHECK %s' % (inv or 'none'))
P('')
if inv: row = 'Invalid'
elif not R1: row = 'Not confirmed (R1 fails: the limit does not work as traced)'
elif REF and R5: row = 'Refuted'
elif R2 and not R5: row = 'Not confirmed (no working positive control)'
elif R2 and R3 and R4 and R5: row = 'Confirmed'
elif R2 and R5 and not R3: row = 'Not confirmed (partial: H2 not shown%s)' % ('' if R4 else '; R4 also fails')
elif R2 and R3 and R5 and not R4: row = 'Not confirmed (partial: H3 not shown)'
else: row = 'Not confirmed (no matching row)'
P('R1 %s R2 %s R3 %s R4 %s R5 %s REFUTED-CHECK %s' % (R1, R2, R3, R4, R5, REF))
P('MATCHED ROW (S7): %s' % row)
print('\n'.join(out))
