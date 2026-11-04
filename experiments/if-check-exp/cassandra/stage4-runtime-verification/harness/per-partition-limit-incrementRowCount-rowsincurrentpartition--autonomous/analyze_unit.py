#!/usr/bin/env python3
"""Analyzer of the unit tier (B2f / B2g as amended 2026-10-27) of per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.
Usage: analyze_unit.py unit.txt [source]. Prints EXPECTED lines (ok / MISMATCH). Thresholds are the frozen B2f text."""
import sys, statistics, collections
d = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if '=' in l: k, v = l.split('=', 1); d[k] = v
SRC = int(sys.argv[2]) if len(sys.argv) > 2 else int(d.get('SOURCE', 20000)); REPS = int(d.get('REPS', 5))
mism = 0
def E(name, ok, detail=''):
    global mism
    if not ok: mism += 1
    print('EXPECTED %s: %s %s' % (name, 'ok' if ok else 'MISMATCH', detail))
def g(k): return int(d[k]) if k in d else None
def med(vals): vals = [v for v in vals if v is not None]; return statistics.median(vals) if vals else None
E('first trigger (warm w=16 n=100: rowsCounted 100, inPart 100, out 100, isDone false)', g('warm.rowsCounted') == 100 and g('warm.out') == 100 and g('warm.inPart') == 100 and d.get('warm.isDone') == 'false',
  'rowsCounted=%s inPart=%s out=%s isDone=%s' % (d.get('warm.rowsCounted'), d.get('warm.inPart'), d.get('warm.out'), d.get('warm.isDone')))
E('run finished (done=1)', d.get('done') == '1')
ooms = [k for k in d if k.endswith('.oom')]
E('no OutOfMemoryError', not ooms, str(ooms))
pts = collections.defaultdict(list)   # (w, n) -> keys
for k in d:
    p = k.split('.')
    if p[0] == 'P' and p[3].startswith('r') and p[4] == 'rowsCounted': pts[(int(p[1][1:]), int(p[2][1:]))].append('.'.join(p[:4]))
bad = []
for (w, L), ks in sorted(pts.items()):
    for k in ks:
        ok = g(k + '.rowsCounted') == L and g(k + '.out') == L and g(k + '.inPart') == L and d.get(k + '.isDone') == 'false' and g(k + '.outLive') == L
        if not ok: bad.append(k)
E('rowsCounted == inPart == out == n, isDone false (all pairs, all reps; %d pairs)' % len(pts), not bad and len(pts) > 0, 'bad=%s' % bad[:5])
nb = [k for k in d if k.startswith('NONE.') and k.endswith('.out') and g(k) != SRC]
E('NONE: output == source (%d)' % SRC, not nb and any(k.startswith('NONE.') for k in d), str(nb))
def R(w, L, what='retained'): return med([g('P.w%d.L%d.r%d.%s' % (w, L, r, what)) for r in range(1, REPS + 1)])
for what in ('retained', 'unshared'):
    m = {}
    for w in (16, 1024, 65536):
        a, b = R(w, 100, what), R(w, 1000, what)
        m[w] = (b - a) / 900.0 if a is not None and b is not None else None
    print('m(w) [%s]: %s' % (what, {w: (round(v, 1) if v is not None else None) for w, v in m.items()}))
    if all(v is not None for v in m.values()):
        E('B2f slope w=1024 (%s): 0.95 x 1008 <= m(1024) - m(16) <= 1.1 x 1008 + 64' % what, 0.95 * 1008 <= m[1024] - m[16] <= 1.1 * 1008 + 64, '%.1f' % (m[1024] - m[16]))
        E('B2f slope w=65536 (%s): 0.95 x 65520 <= m(65536) - m(16) <= 1.1 x 65520 + 64' % what, 0.95 * 65520 <= m[65536] - m[16] <= 1.1 * 65520 + 64, '%.1f' % (m[65536] - m[16]))
        E('B2f ratio m(65536) / m(16) >= 50 (%s)' % what, m[16] > 0 and m[65536] / m[16] >= 50, '%.1f' % (m[65536] / m[16] if m[16] else float('nan')))
        print('INFO flat-across-widths (refuting) condition m(65536)-m(16) < 0.1 x 65520: %s' % (m[65536] - m[16] < 0.1 * 65520))
    else: E('B2f slope (%s): readings present' % what, False)
for w in (16, 1024):
    a, b, c = R(w, 100), R(w, 1000), R(w, 10000)
    if None in (a, b, c): E('B2f linear in n, w=%d: readings present' % w, False); continue
    ratio = (c - b) / (10 * (b - a)) if b != a else float('nan')
    E('B2f linear in n w=%d: (R(10000)-R(1000)) within 0.9..1.1 of 10 x (R(1000)-R(100))' % w, 0.9 <= ratio <= 1.1, 'ratio %.3f' % ratio)
# dead rows
dead_ok = True; det = []
for L in (1, 100, 1000):
    for r in range(1, REPS + 1):
        k = 'DEAD.w16.L%d.r%d' % (L, r)
        if k + '.rowsCounted' not in d: continue
        ok = g(k + '.rowsCounted') == L and g(k + '.outLive') == L and 10 * L - 9 <= g(k + '.pulled') <= 10 * L + 1
        if not ok: dead_ok = False; det.append((k, d.get(k + '.rowsCounted'), d.get(k + '.outLive'), d.get(k + '.pulled')))
E('B2f dead rows: rowsCounted == outLive == n, 10n-9 <= pulled <= 10n+1', dead_ok and any(k.startswith('DEAD.') for k in d), str(det[:3]))
# many partitions
mok = True; mdet = []; seen = False
for n in (1, 10, 100):
    for r in range(1, REPS + 1):
        k = 'MANY.n%d.r%d' % (n, r)
        if k + '.out' not in d: continue
        seen = True
        ok = g(k + '.out') == 20 * n and g(k + '.rowsCounted') == 20 * n and g(k + '.started') == 20 and 20 * n <= g(k + '.pulled') <= 20 * n + 20
        if not ok: mok = False; mdet.append((k, d.get(k + '.out'), d.get(k + '.rowsCounted'), d.get(k + '.started'), d.get(k + '.pulled')))
E('B2f many partitions: out == rowsCounted == 20 x n, 20 partitions started, 20n <= pulled <= 20n+20', mok and seen, str(mdet[:3]))
gok = True; gdet = []; seen = False
for r in range(1, REPS + 1):
    k = 'GLOBAL.g10.r%d' % r
    if k + '.out' not in d: continue
    seen = True
    if not (g(k + '.out') == 10 and g(k + '.rowsCounted') == 10 and g(k + '.started') == 1): gok = False; gdet.append((k, d.get(k + '.out'), d.get(k + '.rowsCounted'), d.get(k + '.started')))
E('B2f global cqlLimits(10) on 20 partitions: out == rowsCounted == 10, one partition started', gok and seen, str(gdet[:3]))
# control
lo = 8 << 20
cok = True; cdet = []; heaps = {}
for w in (16, 1024, 65536):
    for r in range(1, REPS + 1):
        k = 'CTL.w%d.r%d' % (w, r)
        if k + '.unshared' not in d: cok = False; cdet.append((k, 'missing')); continue
        u = g(k + '.unshared'); rows = g(k + '.rows'); rowsz = u / rows
        if not (lo <= u < lo + rowsz + 1): cok = False; cdet.append((k, 'unshared', u))
        heaps.setdefault(w, []).append(g(k + '.retained'))
        if not (0.8 * u <= g(k + '.retained') <= 1.3 * (lo + rowsz)): cok = False; cdet.append((k, 'retained', g(k + '.retained'), lo + rowsz))
E('B2f/B2h control: unshared sum in [8 MiB, 8 MiB + one row), retained heap within 0.8 x unshared..1.3 x (8 MiB + row)', cok, str(cdet[:4]))
print('INFO control retained medians (bytes):', {w: med(v) for w, v in heaps.items()})
print('SUMMARY mismatches=%d' % mism)
