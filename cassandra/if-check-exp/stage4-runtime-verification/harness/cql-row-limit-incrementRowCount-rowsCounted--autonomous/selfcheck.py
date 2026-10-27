#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files (does not import the analyzers; uses different formulas where possible). Usage: selfcheck.py <run1-dir>
Unit: re-reads unit.txt line by line. Cluster: re-reads alloc.csv and queries.jsonl; the allocation of a query is the interpolated cumulative counter at
t1+1000 ms minus at t0, minus the idle rate of the 1 s before t0 (the analyzer uses the nearest samples). Prints values for results section 5."""
import sys, os, json, statistics, collections
root = sys.argv[1]
def kv(path):
    d = {}
    for l in open(path):
        if '=' in l: k, v = l.rstrip('\n').split('=', 1); d[k] = v
    return d
u = kv(os.path.join(root, 'unit/raw/unit.txt'))
print('UNIT keys', len(u), 'done', u.get('done'), 'source', u.get('SOURCE'), 'oom keys', [k for k in u if k.endswith('.oom')])
def med(w, L, what):
    v = [int(u['P.w%d.L%d.r%d.%s' % (w, L, r, what)]) for r in range(1, 6) if 'P.w%d.L%d.r%d.%s' % (w, L, r, what) in u]
    return statistics.median(v) if v else None, v
for w, Ls in ((16, (1, 100, 1000, 10000, 1000000)), (1024, (1, 100, 1000, 10000)), (65536, (1, 100, 1000))):
    for L in Ls:
        m, v = med(w, L, 'retained'); un, _ = med(w, L, 'unshared'); rc = {u.get('P.w%d.L%d.r%d.rowsCounted' % (w, L, r)) for r in range(1, 6)}; out = {u.get('P.w%d.L%d.r%d.out' % (w, L, r)) for r in range(1, 6)}
        print('UNIT w=%d L=%d retained median %s (reps %s) unshared %s rowsCounted %s out %s' % (w, L, m, v, un, rc, out))
for L in (1, 100, 1000):
    print('UNIT dead L=%d' % L, [(u.get('DEAD.w16.L%d.r%d.rowsCounted' % (L, r)), u.get('DEAD.w16.L%d.r%d.outLive' % (L, r)), u.get('DEAD.w16.L%d.r%d.pulled' % (L, r))) for r in range(1, 6)])
print('UNIT NONE out', [u.get('NONE.w16.r%d.out' % r) for r in range(1, 6)], 'retained', [u.get('NONE.w16.r%d.retained' % r) for r in range(1, 6)])
for w in (16, 1024, 65536):
    print('UNIT ctl w=%d' % w, [(u.get('CTL.w%d.r%d.rows' % (w, r)), u.get('CTL.w%d.r%d.unshared' % (w, r)), u.get('CTL.w%d.r%d.retained' % (w, r))) for r in range(1, 6)])
# cluster
def samples(p):
    t, a, h = [], [], []
    for l in open(p):
        x = l.strip().split(',')
        if len(x) == 3 and x[0].isdigit(): t.append(int(x[0])); a.append(int(x[1])); h.append(int(x[2]))
    return t, a, h
def cum(S, x):
    t, a, h = S; lo, hi = 0, len(t) - 1
    if x <= t[0]: return a[0]
    if x >= t[-1]: return a[-1]
    while hi - lo > 1:
        m = (lo + hi) // 2
        if t[m] <= x: lo = m
        else: hi = m
    return a[lo] + (a[hi] - a[lo]) * (x - t[lo]) / float(t[hi] - t[lo])
res = {}
for life in ('U', 'C'):
    d = os.path.join(root, 'cluster', life)
    if not os.path.exists(d + '/queries.jsonl'): continue
    S = samples(d + '/alloc.csv'); Q = [json.loads(l) for l in open(d + '/queries.jsonl')]
    print('CLUSTER life %s: %d samples, %d queries, sample gap median %d ms' % (life, len(S[0]), len(Q), statistics.median(b - a for a, b in zip(S[0], S[0][1:]))))
    g = collections.defaultdict(list)
    for q in Q:
        if q.get('warm') or q.get('trigger'): continue
        rate = (cum(S, q['t0_ms'] - 200) - cum(S, q['t0_ms'] - 1200)) / 1000.0
        A = cum(S, q['t1_ms'] + 1000) - cum(S, q['t0_ms']) - rate * (q['t1_ms'] + 1000 - q['t0_ms'])
        g[(q['table'], q['L'], q['fetch'])].append((A, q['rows'], q['pages'], q['err'], q['bytes']))
    for k in sorted(g, key=lambda k: (k[0], str(k[1]), k[2])):
        v = g[k]; res[(life,) + k] = statistics.median(a for a, *_ in v)
        print('  %s %s L=%s fetch=%s: A median %d (reps %s) rows %s pages %s err %s' % (life, k[0], k[1], k[2], res[(life,) + k], [int(a) for a, *_ in v], {r for _, r, *_ in v}, {p for _, _, p, *_ in v}, {(e or '-')[:40] for *_, e, b in v}))
    # per-page for the paged t_big query
    for q in Q:
        if q['fetch'] == '100' and not q.get('warm') and not q.get('trigger'):
            pa = [cum(S, e) - cum(S, s) for s, e in q['pages_ms']]; print('  paged t_big rep %s per-page A (MB): %s' % (q.get('rep'), [round(x / 1e6, 1) for x in pa]))
a = lambda t: (res[('U', t, '1000', 'none')] - res[('U', t, '10', 'none')]) / 990.0
try:
    print('SLOPES a(t):', {t: round(a(t)) for t in ('t_small', 't_med', 't_big')}, 'diffs', round(a('t_med') - a('t_small')), round(a('t_big') - a('t_med')))
except KeyError as e: print('SLOPES not computable', e)
