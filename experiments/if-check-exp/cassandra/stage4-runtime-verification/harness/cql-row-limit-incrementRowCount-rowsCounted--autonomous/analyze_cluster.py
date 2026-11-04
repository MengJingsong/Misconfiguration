#!/usr/bin/env python3
"""Analyzer of the cluster tier (B3f / B3g as amended 2026-10-27). Usage: analyze_cluster.py <outdir>   (outdir has U/ and C/ with alloc.csv and queries.jsonl)
Also imported by cluster-run.py (window_alloc) for its first-trigger checks. Prints EXPECTED lines (ok / MISMATCH)."""
import sys, os, json, bisect, statistics, collections
ROWS = {'t_small': 120000, 't_med': 1200, 't_big': 1200}
WIDTH = {'t_small': 100, 't_med': 10240, 't_big': 102400}

def load_samples(path):
    ts, al, hp = [], [], []
    for l in open(path):
        p = l.strip().split(',')
        if len(p) != 3 or not p[0].isdigit(): continue
        ts.append(int(p[0])); al.append(int(p[1])); hp.append(int(p[2]))
    return ts, al, hp

def _last_le(ts, t): i = bisect.bisect_right(ts, t) - 1; return i if i >= 0 else None
def _first_ge(ts, t): i = bisect.bisect_left(ts, t); return i if i < len(ts) else None

def drift_rate(S, t0):
    ts, al, hp = S
    a, b = _first_ge(ts, t0 - 1200), _last_le(ts, t0 - 200)
    if a is None or b is None or b <= a: return 0.0
    return (al[b] - al[a]) / float(ts[b] - ts[a])

def window_alloc(S, t_start, t_end, t0_for_drift=None, settle=1000):
    """bytes allocated between the last sample <= t_start and the first sample >= t_end + settle, minus idle drift."""
    ts, al, hp = S
    i, j = _last_le(ts, t_start), _first_ge(ts, t_end + settle)
    if i is None or j is None: return None
    raw = al[j] - al[i]
    return raw - drift_rate(S, t0_for_drift if t0_for_drift is not None else t_start) * (ts[j] - ts[i])

def window_heap(S, t0, t1):
    ts, al, hp = S
    a, b = _first_ge(ts, t0), _last_le(ts, t1 + 300)
    base = [hp[k] for k in range(_first_ge(ts, t0 - 1000) or 0, (_last_le(ts, t0) or 0) + 1)]
    if a is None or b is None or b < a or not base: return None
    return max(hp[a:b + 1]) - statistics.median(base)

def _cum(S, t):
    """cumulative allocation at time t, linear between the two samples around t."""
    ts, al, hp = S
    k = bisect.bisect_right(ts, t)
    if k <= 0: return float(al[0])
    if k >= len(ts): return float(al[-1])
    f = (t - ts[k - 1]) / float(ts[k] - ts[k - 1]); return al[k - 1] + f * (al[k] - al[k - 1])

def page_allocs(S, q):
    """per-page allocation: the cumulative counter interpolated linearly between samples (samples are about 26 ms apart and a page takes 40-80 ms,
    so a sample-to-sample window would double count the neighbours), minus the idle drift."""
    out = []
    for (s, e) in q['pages_ms']:
        out.append(_cum(S, e) - _cum(S, s) - drift_rate(S, q['t0_ms']) * (e - s))
    return out

def read_life(d):
    S = load_samples(os.path.join(d, 'alloc.csv')); Q = [json.loads(l) for l in open(os.path.join(d, 'queries.jsonl'))]
    for q in Q:
        q['A'] = window_alloc(S, q['t0_ms'], q['t1_ms']); q['H'] = window_heap(S, q['t0_ms'], q['t1_ms']); q['pageA'] = page_allocs(S, q) if q.get('pages', 0) > 1 else []
    return Q

def main(root):
    if os.environ.get('STAGE4_SCALE') == 'small': ROWS.update({'t_small': 12000, 't_med': 1200, 't_big': 300})
    mism = [0]
    def E(name, ok, detail=''):
        if not ok: mism[0] += 1
        print('EXPECTED %s: %s %s' % (name, 'ok' if ok else 'MISMATCH', detail))
    U = read_life(os.path.join(root, 'U')); C = os.path.join(root, 'C')
    Cq = read_life(C) if os.path.exists(os.path.join(C, 'queries.jsonl')) else []
    def sel(Q, table, L, fetch='none'):
        return [q for q in Q if q['table'] == table and q['L'] == str(L) and q['fetch'] == str(fetch) and not q.get('warm') and not q.get('trigger')]
    def A(Q, table, L, fetch='none'):
        v = [q['A'] for q in sel(Q, table, L, fetch) if q['A'] is not None and not q['err']]
        return statistics.median(v) if v else None
    # 1 rows
    bad = []
    for q in U:
        if q.get('warm'): continue
        want = ROWS[q['table']] if q['L'] == 'none' else min(int(q['L']), ROWS[q['table']])
        if q['err'] or q['rows'] != want or q['bytes'] != want * WIDTH[q['table']]: bad.append((q['table'], q['L'], q['fetch'], q['rows'], q['err']))
    E('rows returned == min(LIMIT, rows in partition), payload bytes == rows x width, no error (lifetime U, %d queries)' % len([q for q in U if not q.get('warm')]), not bad and len(U) > 0, str(bad[:4]))
    # 2 width
    a = {}
    for t in ROWS:
        x, y = A(U, t, 1000), A(U, t, 10)
        a[t] = (x - y) / 990.0 if x is not None and y is not None else None
    print('a(t) marginal allocated bytes per row [A(1000)-A(10)]/990:', {t: (round(v, 1) if v is not None else None) for t, v in a.items()})
    if None not in a.values():
        d1, d2 = a['t_med'] - a['t_small'], a['t_big'] - a['t_med']
        E('B3f width: a(t_med)-a(t_small) in [1.0, 10] x 10140', 10140 <= d1 <= 101400, '%.0f (x%.2f)' % (d1, d1 / 10140.0))
        E('B3f width: a(t_big)-a(t_med) in [1.0, 10] x 92160', 92160 <= d2 <= 921600, '%.0f (x%.2f)' % (d2, d2 / 92160.0))
        print('INFO refuting condition (flat across widths): d1 < 0.1 x 10140: %s ; d2 < 0.1 x 92160: %s' % (d1 < 1014, d2 < 9216))
    else: E('B3f width: readings present', False)
    As = [A(U, t, 1000) for t in ('t_small', 't_med', 't_big')]
    E('B3f A(small,1000) < A(med,1000) < A(big,1000) and A(big,1000) >= 100 MB', None not in As and As[0] < As[1] < As[2] and As[2] >= 100e6, str([None if v is None else int(v) for v in As]))
    # 3 LIMIT
    Ls = {'t_small': [10, 100, 1000, 10000, 100000], 't_med': [10, 100, 1000], 't_big': [10, 100, 1000]}
    for t, ls in Ls.items():
        v = [A(U, t, L) for L in ls]
        E('B3f LIMIT: A(%s, n) increases with n' % t, None not in v and all(v[i] < v[i + 1] for i in range(len(v) - 1)), str([None if x is None else int(x) for x in v]))
    def mg(t, l1, l2): x, y = A(U, t, l2), A(U, t, l1); return (x - y) / float(l2 - l1) if x is not None and y is not None else None
    for t, (p, q_) in {'t_small': ((1000, 10000), (10000, 100000)), 't_med': ((10, 100), (100, 1000)), 't_big': ((10, 100), (100, 1000))}.items():
        m1, m2 = mg(t, *p), mg(t, *q_)
        E('B3f LIMIT: marginal bytes per row of %s between %s and between %s within 0.5..2 x' % (t, p, q_), m1 is not None and m2 is not None and 0.5 <= m2 / m1 <= 2, 'm1=%s m2=%s' % (m1, m2))
    # 4 none
    an, a1 = A(U, 't_big', 'none'), A(U, 't_big', 1000)
    E('B3f none: A(t_big, none) > A(t_big, 1000)', an is not None and a1 is not None and an > a1, '%s vs %s' % (an, a1))
    # 5 paging
    pq = sel(U, 't_big', 1000, 100); au = a1
    if pq and au:
        tot = statistics.median([q['A'] for q in pq]); mp = statistics.median([max(q['pageA']) for q in pq if q['pageA']] or [float('nan')])
        E('B3f paging: t_big n=1000 fetch 100: rows 1000, 10 (or 11) pages', all(q['rows'] == 1000 and q['pages'] in (10, 11) and not q['err'] for q in pq), str([(q['rows'], q['pages']) for q in pq]))
        E('B3f paging: total A within 0.5..2 x unpaged', 0.5 <= tot / au <= 2, 'total %d unpaged %d' % (tot, au))
        E('B3f paging: largest page A <= 0.25 x unpaged A', mp <= 0.25 * au, 'max page %d, 0.25 x unpaged %d' % (mp, 0.25 * au))
    else: E('B3f paging readings present', False)
    ps = sel(U, 't_small', 100000, 5000)
    E('B3f paging: t_small n=100000 fetch 5000: rows 100000 in 20 (or 21) pages', bool(ps) and all(q['rows'] == 100000 and q['pages'] in (20, 21) and not q['err'] for q in ps), str([(q['rows'], q['pages'], q['err']) for q in ps][:3]))
    # 6 control
    if Cq:
        for t, L in (('t_big', 1000), ('t_big', 'none')):
            qs = sel(Cq, t, L)
            E('B3f control: %s n=%s fails on every repeat with a read-size abort' % (t, L), len(qs) == 3 and all(q['err'] and ('size' in q['err'].lower() or 'read_size' in json.dumps(q.get('err_codes', {})).lower()) for q in qs), str([(q['err'] or '')[:90] for q in qs]))
        for t, L in (('t_big', 100), ('t_med', 1000), ('t_small', 100000)):
            qs = sel(Cq, t, L); ac, au_ = A(Cq, t, L), A(U, t, L)
            want = min(int(L), ROWS[t])
            E('B3f control: %s n=%s passes with the full answer, A within 0.5..2 x of lifetime U' % (t, L), len(qs) == 3 and all(not q['err'] and q['rows'] == want for q in qs) and ac and au_ and 0.5 <= ac / au_ <= 2, 'A_C=%s A_U=%s' % (ac, au_))
        c1, cn = A(Cq, 't_big', 1000), A(Cq, 't_big', 'none')
        # a failed query has q['err']; its A is still measured, so use the raw values
        def Araw(Q, t, L): v = [q['A'] for q in sel(Q, t, L) if q['A'] is not None]; return statistics.median(v) if v else None
        c1, cn = Araw(Cq, 't_big', 1000), Araw(Cq, 't_big', 'none')
        E('B3f control: A_C(t_big,1000) <= 0.5 x A_U(t_big,1000)', c1 is not None and a1 is not None and c1 <= 0.5 * a1, 'A_C=%s A_U=%s' % (c1, a1))
        E('B3f control: A_C(t_big,1000) within 0.5..2 x of A_C(t_big,none)', c1 is not None and cn is not None and 0.5 <= c1 / cn <= 2, 'A_C(1000)=%s A_C(none)=%s' % (c1, cn))
    else: E('B3f control readings present (lifetime C)', False)
    # per-query table for the record
    print('\nTABLE life table L fetch rep rows pages err A_bytes H_bytes')
    for tag, Q in (('U', U), ('C', Cq)):
        for q in Q:
            print('ROW', tag, q['table'], q['L'], q['fetch'], q.get('rep'), q['rows'], q['pages'], (q['err'] or '-')[:60].replace(' ', '_'), None if q['A'] is None else int(q['A']), None if q['H'] is None else int(q['H']), '(warm)' if q.get('warm') else ('(trigger)' if q.get('trigger') else ''))
    print('SUMMARY mismatches=%d' % mism[0])

if __name__ == '__main__': main(sys.argv[1])
