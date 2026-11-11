#!/usr/bin/env python3
"""Harness summary (not the self-check) for the cluster tier of sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous.
usage: summarize.py <start dir>          per-phase readings of one start from samples.csv, phases.txt and client JSON
       summarize.py --cross <run dir>    cross-start relations of B3f (amended)
"""
import csv, json, os, re, statistics, sys


def load_start(d):
    rows = list(csv.DictReader(open(os.path.join(d, 'samples.csv'))))
    for r in rows:
        for k, v in list(r.items()):
            if k != 'phase':
                try:
                    r[k] = int(v)
                except (TypeError, ValueError):
                    r[k] = None
    cur = os.path.basename(d.rstrip('/'))
    ph = {}
    for line in open(os.path.join(os.path.dirname(d.rstrip('/')), 'phases.txt')):
        f = line.split()
        if len(f) < 3 or f[0] != cur:
            continue
        kv = dict(x.split('=', 1) for x in f[2:] if '=' in x)
        ph.setdefault(f[1], {}).update({k: int(v) for k, v in kv.items()})
    return cur, rows, ph


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def phase_summary(cur, rows, ph, d):
    out = []
    order = []
    for r in rows:
        if r['phase'] not in order:
            order.append(r['phase'])
    for p in order:
        rs = [r for r in rows if r['phase'] == p]
        line = 'SUM %s %s n=%d W=[%s,%s] Rntr_max=%s ntrA_max=%s readA_max=%s' % (
            cur, p, len(rs), min(r['W'] for r in rs), max(r['W'] for r in rs), max(r['R_ntr'] for r in rs),
            max((r['ntr_active'] or 0) for r in rs), max((r['read_active'] or 0) for r in rs))
        info = ph.get(p, {})
        if 'client_t_start' in info:
            st = [r for r in rs if info['client_t_start'] + 30000 <= r['t_ms'] <= info['client_t_end']]
            pk = max(rs, key=lambda r: (r['W'], r['t_ms']))
            line += ' steady_n=%d med_ntrA=%s med_Rntr=%s med_ntrP=%s med_readA=%s | peak t=%d W=%d T=%s S=%s Sc=%s rss=%s' % (
                len(st), med([r['ntr_active'] for r in st]), med([r['R_ntr'] for r in st]), med([r['ntr_pending'] for r in st]),
                med([r['read_active'] for r in st]), pk['t_ms'], pk['W'], pk['nmt_threads'], pk['nmt_stack_res_kb'],
                pk['nmt_stack_com_kb'], pk['rss_kb'])
            try:
                pj = json.load(open(os.path.join(d, p, 'phase.json')))
                ws = [json.load(open(os.path.join(d, p, f))) for f in sorted(os.listdir(os.path.join(d, p))) if re.match(r'w\d+\.json$', f)]
                line += ' | client ok=%s err=%s reconnects=%s inflight_medians=%s left=%s' % (
                    pj['totals'].get('ok'), pj['totals'].get('err'), pj['totals'].get('reconnects'),
                    [w.get('inflight_median') for w in ws], pj['totals'].get('left_inflight'))
            except Exception as e:  # noqa: BLE001
                line += ' | client ? (%s)' % e
        if p.startswith('idle') or p == 'postshrink-idle':
            ss = [r['nmt_stack_res_kb'] for r in rs if r['nmt_stack_res_kb'] is not None]
            line += ' | last: W=%d T=%s S=%s rss=%s; S drift=%s KB' % (rs[-1]['W'], rs[-1]['nmt_threads'], rs[-1]['nmt_stack_res_kb'],
                                                                       rs[-1]['rss_kb'], (max(ss) - min(ss)) if ss else None)
        out.append(line)
    return out


def peak(rows, p):
    rs = [r for r in rows if r['phase'] == p]
    return max(rs, key=lambda r: (r['W'], r['t_ms'])) if rs else None


def cross(run):
    st = {}
    for lab in ('k16', 'k64', 'k128', 'k256', 'X'):
        d = os.path.join(run, lab)
        if os.path.exists(os.path.join(d, 'samples.csv')):
            st[lab] = load_start(d)
    out = []
    wm = {}
    for lab, (cur, rows, ph) in st.items():
        p = peak(rows, 'C400')
        wm[lab] = p
        idle = [r for r in rows if r['phase'] == 'idle']
        out.append('CROSS %s W_max_C400=%d T=%s S=%s rss=%s W_idle_last=%d' % (lab, p['W'], p['nmt_threads'], p['nmt_stack_res_kb'], p['rss_kb'], idle[-1]['W']))
    if 'k16' in wm and 'k256' in wm:
        a, b = wm['k16'], wm['k256']
        dW, dT, dS = b['W'] - a['W'], b['nmt_threads'] - a['nmt_threads'], b['nmt_stack_res_kb'] - a['nmt_stack_res_kb']
        out.append('CROSS dW(16->256)=%d dT=%d dS=%d KB dS/dT=%.1f KB dRSS=%d KB' % (dW, dT, dS, dS / dT if dT else float('nan'), b['rss_kb'] - a['rss_kb']))
    if 'X' in st and 'k256' in st:
        sl = {}
        for lab in ('k256', 'X'):
            cur, rows, ph = st[lab]
            p = peak(rows, 'C400')
            i = [r for r in rows if r['phase'] == 'idle'][-1]
            sl[lab] = ((p['nmt_stack_res_kb'] - i['nmt_stack_res_kb']) / (p['nmt_threads'] - i['nmt_threads']), p['nmt_threads'] - i['nmt_threads'])
        out.append('CROSS slope k256=%.1f KB/thread (dT=%d) X=%.1f KB/thread (dT=%d) ratio=%.3f' % (sl['k256'][0], sl['k256'][1], sl['X'][0], sl['X'][1], sl['X'][0] / sl['k256'][0]))
    return out


if __name__ == '__main__':
    if sys.argv[1] == '--cross':
        print('\n'.join(cross(sys.argv[2])))
    else:
        d = sys.argv[1]
        cur, rows, ph = load_start(d)
        print('\n'.join(phase_summary(cur, rows, ph, d)))
