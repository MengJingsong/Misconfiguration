#!/usr/bin/env python3
"""Analyzer of the cluster tier (B3f / B3g as amended 2026-10-27) of per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.
Usage: analyze_cluster.py <outdir>   (outdir has U/ and C/ with alloc.csv, queries.jsonl; U/du.txt). Also imported by cluster-run.py. Prints EXPECTED lines (ok / MISMATCH)."""
import sys, os, json, bisect, statistics
P = 4
PP = {'t_small': 30000, 't_med': 300, 't_big': 300}          # rows per partition
WIDTH = {'t_small': 100, 't_med': 10240, 't_big': 102400}
def want_rows(t, n): return P * (PP[t] if n == 'none' else min(int(n), PP[t]))

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
def window_alloc(S, t_start, t_end, settle=1000):
    """bytes allocated from the last sample <= t_start to the first sample >= t_end + settle, minus idle drift."""
    ts, al, hp = S
    i, j = _last_le(ts, t_start), _first_ge(ts, t_end + settle)
    if i is None or j is None: return None
    return al[j] - al[i] - drift_rate(S, t_start) * (ts[j] - ts[i])
def window_heap(S, t0, t1):
    ts, al, hp = S
    a, b = _first_ge(ts, t0), _last_le(ts, t1 + 300)
    base = [hp[k] for k in range(_first_ge(ts, t0 - 1000) or 0, (_last_le(ts, t0) or 0) + 1)]
    if a is None or b is None or b < a or not base: return None
    return max(hp[a:b + 1]) - statistics.median(base)
def page_allocs(S, q):
    ts, al, hp = S; out = []
    for (s, e) in q['pages_ms']:
        i, j = _last_le(ts, s), _first_ge(ts, e)
        if i is None or j is None: continue
        out.append(al[j] - al[i] - drift_rate(S, q['t0_ms']) * (ts[j] - ts[i]))
    return out
def read_life(d):
    S = load_samples(os.path.join(d, 'alloc.csv')); Q = [json.loads(l) for l in open(os.path.join(d, 'queries.jsonl'))]
    for q in Q:
        q['A'] = window_alloc(S, q['t0_ms'], q['t1_ms']); q['H'] = window_heap(S, q['t0_ms'], q['t1_ms']); q['pageA'] = page_allocs(S, q) if q.get('pages', 0) > 1 else []
    return Q
def is_abort(q): return bool(q['err']) and ('size' in q['err'].lower() or 'read_size' in json.dumps(q.get('err_codes', {})).lower() or 'read size' in q['err'].lower())

def main(root):
    mism = [0]
    def E(name, ok, detail=''):
        if not ok: mism[0] += 1
        print('EXPECTED %s: %s %s' % (name, 'ok' if ok else 'MISMATCH', detail))
    U = read_life(os.path.join(root, 'U')); C = os.path.join(root, 'C')
    Cq = read_life(C) if os.path.exists(os.path.join(C, 'queries.jsonl')) else []
    def sel(Q, table, L, fetch='none'):
        return [q for q in Q if q['table'] == table and q['L'] == str(L) and q['fetch'] == str(fetch) and not q.get('warm') and not q.get('trigger')]
    def A(Q, table, L, fetch='none', failed_ok=False):
        v = [q['A'] for q in sel(Q, table, L, fetch) if q['A'] is not None and (failed_ok or not q['err'])]
        return statistics.median(v) if v else None
    # 1 rows
    bad = []
    for q in U:
        if q.get('warm'): continue
        w = want_rows(q['table'], q['L'])
        if q['err'] or q['rows'] != w or q['bytes'] != w * WIDTH[q['table']]: bad.append((q['table'], q['L'], q['fetch'], q['rows'], q['err']))
    E('rows returned == 4 x min(n, rows per partition), payload bytes == rows x width, no error (lifetime U, %d queries)' % len([q for q in U if not q.get('warm')]), not bad and len(U) > 0, str(bad[:4]))
    # 2 width
    a = {}
    for t in PP:
        x, y = A(U, t, 100), A(U, t, 10)
        a[t] = (x - y) / 360.0 if x is not None and y is not None else None
    print('a(t) marginal allocated bytes per row [A(100)-A(10)]/360:', {t: (round(v, 1) if v is not None else None) for t, v in a.items()})
    if None not in a.values():
        d1, d2 = a['t_med'] - a['t_small'], a['t_big'] - a['t_med']
        E('B3f width: a(t_med)-a(t_small) in [1.0, 10] x 10140', 10140 <= d1 <= 101400, '%.0f (x%.2f)' % (d1, d1 / 10140.0))
        E('B3f width: a(t_big)-a(t_med) in [1.0, 10] x 92160', 92160 <= d2 <= 921600, '%.0f (x%.2f)' % (d2, d2 / 92160.0))
        print('INFO refuting condition (flat across widths): d1 < 0.1 x 10140: %s ; d2 < 0.1 x 92160: %s' % (d1 < 1014, d2 < 9216))
    else: E('B3f width: readings present', False)
    As = [A(U, t, 100) for t in ('t_small', 't_med', 't_big')]
    E('B3f A(small,100) < A(med,100) < A(big,100) and A(big,100) >= 40 MB', None not in As and As[0] < As[1] < As[2] and As[2] >= 40e6, str([None if v is None else int(v) for v in As]))
    # 3 n
    Ls = {'t_small': [10, 100, 1000, 10000, 'none'], 't_med': [10, 100, 'none'], 't_big': [10, 100, 'none']}
    for t, ls in Ls.items():
        v = [A(U, t, L) for L in ls]
        E('B3f n: A(%s, n) increases with n (n >= 10 and none)' % t, None not in v and all(v[i] < v[i + 1] for i in range(len(v) - 1)), str([None if x is None else int(x) for x in v]))
    def mg(t, l1, l2):
        x, y = A(U, t, l2), A(U, t, l1)
        r1 = P * (PP[t] if l1 == 'none' else l1); r2 = P * (PP[t] if l2 == 'none' else l2)
        return (x - y) / float(r2 - r1) if x is not None and y is not None else None
    for t, (p, q_) in {'t_small': ((100, 1000), (1000, 10000)), 't_med': ((10, 100), (100, 'none')), 't_big': ((10, 100), (100, 'none'))}.items():
        m1, m2 = mg(t, *p), mg(t, *q_)
        E('B3f n: marginal bytes per row of %s between %s and between %s within 0.5..2 x' % (t, p, q_), m1 is not None and m2 is not None and 0.5 <= m2 / m1 <= 2, 'm1=%s m2=%s' % (m1, m2))
    # 4 none
    an, a1 = A(U, 't_big', 'none'), A(U, 't_big', 100)
    E('B3f none: A(t_big, none) > A(t_big, 100) (1200 rows vs 400)', an is not None and a1 is not None and an > a1, '%s vs %s' % (an, a1))
    # 5 paging
    pq = sel(U, 't_big', 100, 100)
    if pq and a1:
        tot = statistics.median([q['A'] for q in pq]); mp = statistics.median([max(q['pageA']) for q in pq if q['pageA']] or [float('nan')])
        E('B3f paging: t_big n=100 fetch 100: 400 rows in 4 or 5 pages', all(q['rows'] == 400 and q['pages'] in (4, 5) and not q['err'] for q in pq), str([(q['rows'], q['pages']) for q in pq]))
        E('B3f paging: total A within 0.5..2 x unpaged', 0.5 <= tot / a1 <= 2, 'total %d unpaged %d' % (tot, a1))
        E('B3f paging: largest page A <= 0.5 x unpaged A', mp <= 0.5 * a1, 'max page %d, 0.5 x unpaged %d' % (mp, 0.5 * a1))
    else: E('B3f paging readings present', False)
    # 6 disk
    try:
        du = dict(l.split() for l in open(os.path.join(root, 'U', 'du.txt')) if len(l.split()) == 2)
        b, af = int(du['before']), int(du['after'])
        E('B3f disk: du -sb of the data directory unchanged (within 1 %) across lifetime U', abs(af - b) <= 0.01 * b, 'before %d after %d' % (b, af))
    except Exception as ex: E('B3f disk readings present', False, str(ex))
    # 7 control
    if Cq:
        for t, L in (('t_big', 100), ('t_big', 'none')):
            qs = sel(Cq, t, L)
            E('B3f control: %s n=%s fails on every repeat with a read-size abort' % (t, L), len(qs) == 3 and all(is_abort(q) for q in qs), str([(q['err'] or '')[:90] for q in qs]))
        for t, L in (('t_big', 10), ('t_med', 'none'), ('t_small', 10000)):
            qs = sel(Cq, t, L); ac, au_ = A(Cq, t, L), A(U, t, L)
            E('B3f control: %s n=%s passes with the full answer, A within 0.5..2 x of lifetime U' % (t, L), len(qs) == 3 and all(not q['err'] and q['rows'] == want_rows(t, L) for q in qs) and ac is not None and au_ is not None and 0.5 <= ac / au_ <= 2, 'A_C=%s A_U=%s' % (ac, au_))
        c1, cn = A(Cq, 't_big', 100, failed_ok=True), A(Cq, 't_big', 'none', failed_ok=True)
        E('B3f control: A_C(t_big,100) <= 0.5 x A_U(t_big,100)', c1 is not None and a1 is not None and c1 <= 0.5 * a1, 'A_C=%s A_U=%s' % (c1, a1))
        E('B3f control: A_C(t_big,100) within 0.5..2 x of A_C(t_big,none)', c1 is not None and cn is not None and 0.5 <= c1 / cn <= 2, 'A_C(100)=%s A_C(none)=%s' % (c1, cn))
    else: E('B3f control readings present (lifetime C)', False)
    print('\nTABLE life table n fetch rep rows pages err A_bytes H_bytes')
    for tag, Q in (('U', U), ('C', Cq)):
        for q in Q:
            print('ROW', tag, q['table'], q['L'], q['fetch'], q.get('rep'), q['rows'], q['pages'], (q['err'] or '-')[:60].replace(' ', '_'), None if q['A'] is None else int(q['A']), None if q['H'] is None else int(q['H']), '(warm)' if q.get('warm') else ('(trigger)' if q.get('trigger') else ''))
    print('SUMMARY mismatches=%d' % mism[0])

if __name__ == '__main__': main(sys.argv[1])
