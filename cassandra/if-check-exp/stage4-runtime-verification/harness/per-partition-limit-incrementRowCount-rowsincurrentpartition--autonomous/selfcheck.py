#!/usr/bin/env python3
"""Independent self-check of run 1 (does not import the analyzers): re-parses the raw logs. Usage: selfcheck.py <run1-dir> (has unit/raw/unit.txt, cluster/{U,C}/)."""
import sys, os, json, re, statistics as st
root = sys.argv[1]; bad = 0
def chk(name, ok, detail=''):
    global bad; bad += (not ok); print('SELFCHECK %s: %s %s' % (name, 'holds' if ok else 'DOES NOT HOLD', detail))
# ---- unit: recompute from raw key=value
d = dict(l.strip().split('=', 1) for l in open(root + '/unit/raw/unit.txt') if '=' in l)
chk('unit finished', d.get('done') == '1')
# every single-partition point: rowsCounted==out==n and inPart==n
pts = sorted({k.rsplit('.', 1)[0] for k in d if k.startswith('P.') and k.endswith('.rowsCounted')})
chk('all %d single-partition points have rowsCounted == out == n' % len(pts), all(int(d[p + '.rowsCounted']) == int(d[p + '.out']) == int(re.search(r'\.L(\d+)\.', p).group(1)) for p in pts))
# rows emitted never above n anywhere (single-partition)
chk('no point emits more than n rows', all(int(d[p + '.out']) <= int(re.search(r'\.L(\d+)\.', p).group(1)) for p in pts))
# slope from raw: marginal retained per row at L=100->1000, per width, median over reps
def med(w, L, what): return st.median(int(d['P.w%d.L%d.r%d.%s' % (w, L, r, what)]) for r in range(1, 6))
for what in ('retained', 'unshared'):
    m = {w: (med(w, 1000, what) - med(w, 100, what)) / 900 for w in (16, 1024, 65536)}
    print('  m(w)[%s] = %s' % (what, {w: round(v, 1) for w, v in m.items()}))
    chk('slope check %s: m(1024)-m(16) in [958, 1172.8], m(65536)-m(16) in [62244, 72136]' % what, 0.95 * 1008 <= m[1024] - m[16] <= 1.1 * 1008 + 64 and 0.95 * 65520 <= m[65536] - m[16] <= 1.1 * 65520 + 64)
# byte-stop control: rows differ across widths, retained flat
c = {w: st.median(int(d['CTL.w%d.r%d.retained' % (w, r)]) for r in range(1, 6)) for w in (16, 1024, 65536)}
r_ = {w: st.median(int(d['CTL.w%d.r%d.rows' % (w, r)]) for r in range(1, 6)) for w in (16, 1024, 65536)}
print('  control retained medians', c, 'rows', r_)
chk('control: retained in [0.8*8MiB, 1.3*(8MiB+row)] for all widths and rows fall with width', all(0.8 * (8 << 20) <= v <= 1.3 * ((8 << 20) + 70000) for v in c.values()) and r_[16] > r_[1024] > r_[65536])
# ---- cluster: re-derive A per query with an independent window rule
def samples(p):
    rows = [l.strip().split(',') for l in open(p) if re.match(r'^\d+,\d+,\d+$', l.strip())]
    return [(int(a), int(b), int(c_)) for a, b, c_ in rows]
def A(S, q):
    t0, t1 = q['t0_ms'], q['t1_ms']
    pre = [s for s in S if s[0] <= t0]; post = [s for s in S if s[0] >= t1 + 1000]
    if not pre or not post: return None
    a, b = pre[-1], post[0]
    idle = [s for s in S if t0 - 1200 <= s[0] <= t0 - 200]
    rate = (idle[-1][1] - idle[0][1]) / max(1, idle[-1][0] - idle[0][0]) if len(idle) > 1 else 0
    return b[1] - a[1] - rate * (b[0] - a[0])
life = {}
for L in 'UC':
    S = samples('%s/cluster/%s/alloc.csv' % (root, L)); Q = [json.loads(l) for l in open('%s/cluster/%s/queries.jsonl' % (root, L))]
    for q in Q: q['A2'] = A(S, q)
    life[L] = Q
    errs = open('%s/cluster/%s/system.log.segment' % (root, L), errors='replace').read()
    chk('lifetime %s: no ERROR line starting a log line, no java.lang.OutOfMemoryError' % L, not re.search(r'^ERROR', errs, re.M) and 'java.lang.OutOfMemoryError' not in errs and 'Java heap space' not in errs)
    print('  lifetime %s: %d queries, %d samples, sample gap max %d ms' % (L, len(Q), len(S), max(b[0] - a[0] for a, b in zip(S, S[1:]))))
def med_(Q, t, n, fetch='none'):
    v = [q['A2'] for q in Q if q['table'] == t and q['L'] == str(n) and q['fetch'] == fetch and not q.get('warm') and not q.get('trigger') and q['A2'] is not None]
    return st.median(v) if v else None
U, C = life['U'], life['C']
chk('U: every non-warm query returned rows = 4 x min(n, rows/partition)', all(q['rows'] == 4 * (({'t_small': 30000, 't_med': 300, 't_big': 300}[q['table']]) if q['L'] == 'none' else min(int(q['L']), {'t_small': 30000, 't_med': 300, 't_big': 300}[q['table']])) and not q['err'] for q in U if not q.get('warm')))
a = {t: (med_(U, t, 100) - med_(U, t, 10)) / 360 for t in ('t_small', 't_med', 't_big')}
print('  a(t) =', {t: round(v) for t, v in a.items()})
chk('width slopes (own windows): a(med)-a(small) in [10140, 101400], a(big)-a(med) in [92160, 921600]', 10140 <= a['t_med'] - a['t_small'] <= 101400 and 92160 <= a['t_big'] - a['t_med'] <= 921600)
# compare own A with analyzer's A (queries.jsonl has no A; the analyzer's summary has ROW lines)
rows = {}
for l in open(root + '/cluster/summary.txt'):
    if l.startswith('ROW '):
        p = l.split(); 
        if p[-1] in ('(warm)', '(trigger)'): continue
        rows.setdefault((p[1], p[2], p[3], p[4]), []).append(int(p[9]) if p[9] != 'None' else None)
diffs = []
for L, Q in (('U', U), ('C', C)):
    for q in Q:
        if q.get('warm') or q.get('trigger'): continue
        k = (L, q['table'], q['L'], q['fetch'])
        pass
mine = {}
for L, Q in (('U', U), ('C', C)):
    for q in Q:
        if q.get('warm') or q.get('trigger'): continue
        mine.setdefault((L, q['table'], q['L'], q['fetch']), []).append(round(q['A2']))
worst = 0
for k, v in mine.items():
    theirs = sorted(x for x in rows.get(k, []) if x is not None)
    if len(theirs) != len(v): diffs.append(k); continue
    for x, y in zip(sorted(v), theirs): worst = max(worst, abs(x - y) / max(1, y))
chk('own per-query A agrees with the analyzer to 1e-4 relative (the analyzer prints truncated integers; worst %.2e), %d shapes' % (worst, len(mine)), not diffs and worst < 1e-4, str(diffs[:3]))
# the control binds: C aborts read-size, with a message naming the threshold
ab = [q for q in C if q['table'] == 't_big' and q['L'] in ('100', 'none') and not q.get('warm')]
chk('control aborts: t_big 100/none queries all failed with code 1300 read failure (%d queries)' % len(ab), all(q['err'] and 'code=1300' in q['err'] for q in ab))
sl = open('%s/cluster/C/system.log.segment' % root, errors='replace').read()
chk('control: system.log names local_read_size_fail_threshold', 'local_read_size_fail_threshold' in sl)
# disk
du = dict(l.split() for l in open(root + '/cluster/U/du.txt'))
chk('disk bytes identical before and after lifetime U', du['before'] == du['after'], str(du))
print('SELFCHECK SUMMARY not-holding=%d' % bad)
