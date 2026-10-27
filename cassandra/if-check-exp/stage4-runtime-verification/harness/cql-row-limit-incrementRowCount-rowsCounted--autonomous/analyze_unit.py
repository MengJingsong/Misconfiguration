#!/usr/bin/env python3
"""Analyzer of the unit tier (B2f / B2g as amended 2026-10-27). Usage: analyze_unit.py unit.txt [source]. Prints EXPECTED lines (ok / MISMATCH)."""
import sys, statistics, collections
d = {}
for l in open(sys.argv[1]):
    l = l.strip()
    if '=' in l: k, v = l.split('=', 1); d[k] = v
SRC = int(sys.argv[2]) if len(sys.argv) > 2 else int(d.get('SOURCE', 1200000)); REPS = int(d.get('REPS', 5))
mism = 0
def E(name, ok, detail=''):
    global mism
    if not ok: mism += 1
    print('EXPECTED %s: %s %s' % (name, 'ok' if ok else 'MISMATCH', detail))
def g(k): return int(d[k]) if k in d else None
def med(vals): vals = [v for v in vals if v is not None]; return statistics.median(vals) if vals else None
E('first trigger (warm w=16 L=100: rowsCounted 100, out 100, isDone)', g('warm.rowsCounted') == 100 and g('warm.out') == 100 and d.get('warm.isDone') == 'true', 'rowsCounted=%s out=%s isDone=%s' % (d.get('warm.rowsCounted'), d.get('warm.out'), d.get('warm.isDone')))
E('run finished (done=1)', d.get('done') == '1')
ooms = [k for k in d if k.endswith('.oom')]
E('no OutOfMemoryError', not ooms, str(ooms))
pts = collections.defaultdict(list)   # (w, L) -> keys
for k in d:
    p = k.split('.')
    if p[0] == 'P' and p[3].startswith('r') and p[4] in ('rowsCounted',): pts[(int(p[1][1:]), int(p[2][1:]))].append('.'.join(p[:4]))
bad = []
for (w, L), ks in sorted(pts.items()):
    for k in ks:
        ok = g(k + '.rowsCounted') == L and g(k + '.out') == L and d.get(k + '.isDone') == 'true' and g(k + '.outLive') == L
        if not ok: bad.append(k)
E('rowsCounted == out == L (all pairs, all reps; %d pairs)' % len(pts), not bad, 'bad=%s' % bad[:5])
nb = [k for k in d if k.startswith('NONE.') and k.endswith('.out') and g(k) != SRC]
E('NONE: output == source (%d)' % SRC, not nb and any(k.startswith('NONE.') for k in d), str(nb))
def R(w, L, what='retained'): return med([g('P.w%d.L%d.r%d.%s' % (w, L, r, what)) for r in range(1, REPS + 1)])
res = {}
def mm(w, what):
    lo, hi, n = ((1000, 10000, 9000.0) if w in (16, 1024) else (100, 1000, 900.0))
    a_, b_ = R(w, lo, what), R(w, hi, what)
    return (b_ - a_) / n if a_ is not None and b_ is not None else None
for what in ('retained', 'unshared'):
    m = {w: mm(w, what) for w in (16, 1024, 65536)}
    res[what] = m
    print('m(w) [%s]: %s' % (what, {w: (round(v, 1) if v is not None else None) for w, v in m.items()}))
    ok = all(m[w] is not None for w in m)
    if ok:
        E('B2f slope w=1024 (%s): 0.9 x 1008 <= m(1024) - m(16) <= 1.15 x 1008 + 64' % what, 0.9 * 1008 <= m[1024] - m[16] <= 1.15 * 1008 + 64, '%.1f' % (m[1024] - m[16]))
        E('B2f slope w=65536 (%s): 0.9 x 65520 <= m(65536) - m(16) <= 1.15 x 65520 + 64' % what, 0.9 * 65520 <= m[65536] - m[16] <= 1.15 * 65520 + 64, '%.1f' % (m[65536] - m[16]))
        E('B2f ratio m(65536) / m(16) >= 50 (%s)' % what, m[16] > 0 and m[65536] / m[16] >= 50, '%.1f' % (m[65536] / m[16] if m[16] else float('nan')))
        print('INFO flat-across-widths (refuting) condition m(65536)-m(16) < 0.1 x 65520: %s' % (m[65536] - m[16] < 0.1 * 65520))
    else: E('B2f slope (%s): readings present' % what, False)
for w, (l1, l2) in ((16, (10000, 1000000)), (65536, (100, 1000))):
    a_, b_ = R(w, l1), R(w, l2)
    if a_ is None or b_ is None: E('B2f linear in L, w=%d: readings present (L=%d, %d; skipped if >= source)' % (w, l1, l2), SRC <= l2); continue
    ratio = (b_ / l2) / (a_ / l1)
    E('B2f linear in L w=%d: retained bytes per row at L=%d and L=%d within 0.75..1.35' % (w, l1, l2), 0.75 <= ratio <= 1.35 and a_ >= 2e6, 'ratio %.3f (R=%d, %d)' % (ratio, a_, b_))
# dead rows
dead_ok = True; det = []
for L in (1, 100, 1000):
    for r in range(1, REPS + 1):
        k = 'DEAD.w16.L%d.r%d' % (L, r)
        if k + '.rowsCounted' not in d: continue
        ok = g(k + '.rowsCounted') == L and g(k + '.outLive') == L and 10 * L - 9 <= g(k + '.pulled') <= 10 * L + 1
        if not ok: dead_ok = False; det.append((k, d.get(k + '.rowsCounted'), d.get(k + '.outLive'), d.get(k + '.pulled')))
E('B2f dead rows: rowsCounted == outLive == L, 10L-9 <= pulled <= 10L+1', dead_ok and any(k.startswith('DEAD.') for k in d), str(det[:3]))
# control
lo, hi = 8 << 20, None
cok = True; cdet = []
heaps = {}
for w in (16, 1024, 65536):
    for r in range(1, REPS + 1):
        k = 'CTL.w%d.r%d' % (w, r)
        if k + '.unshared' not in d: cok = False; cdet.append((k, 'missing')); continue
        u = g(k + '.unshared'); rows = g(k + '.rows'); rowsz = u / rows
        if not (lo <= u < lo + rowsz + 1): cok = False; cdet.append((k, 'unshared', u))
        heaps.setdefault(w, []).append((g(k + '.retained'), u + rowsz))
        if not (0.8 * (u) <= g(k + '.retained') <= 1.3 * (lo + rowsz)): cok = False; cdet.append((k, 'retained', g(k + '.retained'), lo + rowsz))
E('B2f/B2h control: unshared sum in [8 MiB, 8 MiB + one row), retained heap within 0.8 x unshared..1.3 x (8 MiB + row)', cok, str(cdet[:4]))
print('INFO control retained medians (bytes):', {w: med([a for a, b in v]) for w, v in heaps.items()})
print('SUMMARY mismatches=%d' % mism)
