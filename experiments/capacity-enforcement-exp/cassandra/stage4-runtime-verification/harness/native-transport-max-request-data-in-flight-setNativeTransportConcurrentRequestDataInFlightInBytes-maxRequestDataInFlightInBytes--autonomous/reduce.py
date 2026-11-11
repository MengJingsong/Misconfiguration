#!/usr/bin/env python3
"""Reduce one cluster-run arm directory to the readings of the amended B3f (case native-transport-max-request-data-in-flight-setNative...).
usage: reduce.py RUN_DIR L ARM LIVE      L = bytes, or 'default' (107374182), or 1GiB/16MiB/64MiB; LIVE = live|no
Prints key=value lines and EXPECTED: lines (PASS/FAIL per prediction of the amended B3f; no verdict is chosen here)."""
import csv, re, statistics, sys, os
d, Ls, arm, live = sys.argv[1:5]
MiB = 1048576.0
L = {'default': 107374182, '16MiB': 16 * 1048576, '64MiB': 64 * 1048576, '1GiB': 1 << 30}.get(Ls) or int(Ls)
live = live == 'live'
def rows(f):
    with open(os.path.join(d, f)) as fh:
        return [r for r in csv.DictReader(fh) if r.get('t_ms', '').strip().isdigit()]
def kv(f):
    o = {}
    for t in open(os.path.join(d, f)).read().split():
        if '=' in t:
            k, v = t.split('=', 1); o[k] = v
    return o
times = kv('times.txt'); p0 = int(times['probe_start_ms']); c0 = int(times['client_start_ms']); c1 = int(times['client_end_ms'])
base, run = rows('base.csv'), rows('run.csv')
def col(rs, k): return [int(r[k]) for r in rs]
# load window = client start .. client end, in probe-relative ms; drain window continues to the end of the file
w0, w1 = c0 - p0, c1 - p0
load = [r for r in run if w0 <= int(r['t_ms']) <= w1]
b_direct = statistics.median(col(base, 'direct_used'))
b_spread = max(col(base, 'direct_used')) - min(col(base, 'direct_used'))
rs = col(load, 'requests_size'); pa = col(load, 'paused'); du = col(load, 'direct_used'); hu = col(load, 'heap_used')
offered_B = {'v4-256k': 250 * 262144, 'v5-256k': 250 * 262144, 'v5-100k': 640 * 100000}[arm] * 4
out = {'arm': arm, 'L': L, 'live': live, 'offered_bytes': offered_B, 'offered_MiB': round(offered_B / MiB, 1),
       'load_samples': len(load), 'baseline_samples': len(base), 'baseline_direct_median_MiB': round(b_direct / MiB, 2),
       'baseline_direct_spread_MiB': round(b_spread / MiB, 2), 'baseline_requests_size_max': max(col(base, 'requests_size'))}
pk = max(range(len(rs)), key=lambda i: rs[i])
out.update({'peak_requests_size': rs[pk], 'peak_requests_size_MiB': round(rs[pk] / MiB, 2), 'peak_requests_size_t_s': round((int(load[pk]['t_ms']) - w0) / 1000, 1),
            'max_paused': max(pa), 'samples_paused_ge1': sum(1 for x in pa if x >= 1),
            'peak_direct_used_MiB': round(max(du) / MiB, 2), 'delta_direct_MiB': round((max(du) - b_direct) / MiB, 2),
            'peak_heap_MiB': round(max(hu) / MiB, 1)})
# time series every 10 s of load (for the self-check and the live arm)
ser = []
for s in range(0, int((w1 - w0) / 1000) + 1, 10):
    c = [r for r in load if s * 1000 <= int(r['t_ms']) - w0 < (s + 10) * 1000]
    if c: ser.append('%d:%.1f/%.1f/%d' % (s, max(int(r['requests_size']) for r in c) / MiB, (max(int(r['direct_used']) for r in c) - b_direct) / MiB, max(int(r['paused']) for r in c)))
out['series_t_RSmaxMiB_deltaDirectMiB_paused'] = ' '.join(ser)
# NMT Other (KB)
try:
    txt = open(os.path.join(d, 'nmt.txt')).read()
    vals = [int(m.group(1)) for m in re.finditer(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', txt)]
    nb = [int(m.group(1)) for m in re.finditer(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', open(os.path.join(d, 'nmt-base.txt')).read())]
    if vals and nb: out['nmt_other_peak_over_base_MiB'] = round((max(vals) - nb[0]) / 1024, 1)
except FileNotFoundError:
    pass
# histogram totals (live heap)
try:
    for l in open(os.path.join(d, 'hist.txt')):
        m = re.match(r'(hist_\w+): Total\s+(\d+)\s+(\d+)', l)
        if m: out[m.group(1) + '_MiB'] = round(int(m.group(3)) / MiB, 1)
except FileNotFoundError:
    pass
# client result
cl = open(os.path.join(d, 'client.txt')).read()
m = re.search(r'^TOTAL sent=(\d+) ok=(\d+) warned=(\d+) ovl_bytes=(\d+) ovl_other=(\d+) err=(\d+) outstanding=(\d+)', cl, re.M)
if m:
    for k, v in zip(('sent', 'ok', 'warned', 'ovl_bytes', 'ovl_other', 'err', 'outstanding_at_end'), m.groups()): out['client_' + k] = int(v)
    out['client_ok_per_s'] = round(int(m.group(2)) / ((c1 - c0) / 1000.0), 1)
out['hold_lines'] = sum(1 for _ in open(os.path.join(d, 'hold.trace')))
for k, v in out.items(): print('%s=%s' % (k, v))
# EXPECTED lines (amended B3f)
def exp(name, cond, detail): print('EXPECTED: %s: %s (%s)' % (name, 'PASS' if cond else 'FAIL', detail))
if not live:
    bound = 1.5 * L + 6 * MiB
    capped = Ls != '1GiB'
    if capped:
        exp('P1 Peak_RS <= L + 4 MiB', rs[pk] <= L + 4 * MiB, 'peak %.2f MiB, L+4 = %.2f MiB' % (rs[pk] / MiB, (L + 4 * MiB) / MiB))
        exp('P2 Delta <= bound(L) = 1.5 L + 6 MiB', max(du) - b_direct <= bound, 'delta %.2f MiB, bound %.2f MiB' % ((max(du) - b_direct) / MiB, bound / MiB))
        exp('P3 PausedConnections >= 1', max(pa) >= 1, 'max %d' % max(pa))
        exp('P0 limit reached (Peak_RS >= 0.9 L)', rs[pk] >= 0.9 * L, 'peak/L = %.3f' % (rs[pk] / L))
    else:
        exp('P4 control Peak_RS >= 0.8 offered', rs[pk] >= 0.8 * offered_B, 'peak %.1f MiB, offered %.1f MiB' % (rs[pk] / MiB, offered_B / MiB))
        exp('P4 control PausedConnections == 0', max(pa) == 0, 'max %d' % max(pa))
    exp('P3 client other_err == 0', out.get('client_err', -1) == 0 and out.get('client_ovl_other', -1) == 0, 'err %s ovl_other %s' % (out.get('client_err'), out.get('client_ovl_other')))
else:
    ts = int(times['live_set_done_ms']) - p0
    pre = [int(r['requests_size']) for r in run if w0 <= int(r['t_ms']) < int(times['live_set_ms']) - p0]
    exp('live: before the set Peak_RS >= 0.8 offered', max(pre) >= 0.8 * offered_B, 'pre-set peak %.1f MiB, offered %.1f MiB' % (max(pre) / MiB, offered_B / MiB))
    exp('live: global limit read back = 16777216', '16777216' in open(os.path.join(d, 'live-set.txt')).read().split('\n')[-2:][0] or '16777216' in open(os.path.join(d, 'live-set.txt')).read(), 'live-set.txt')
    post = [r for r in run if int(r['t_ms']) >= ts and int(r['t_ms']) <= w1]
    first = next((i for i, r in enumerate(post) if int(r['requests_size']) <= 16 * MiB + 4 * MiB), None)
    exp('live: RequestsSize reaches <= L + 4 MiB within 90 s of the set', first is not None and int(post[first]['t_ms']) - ts <= 90000,
        'first at +%s s' % (None if first is None else round((int(post[first]['t_ms']) - ts) / 1000, 1)))
    if first is not None:
        after = [int(r['requests_size']) for r in post[first:]]
        exp('live: stays <= L + 4 MiB afterwards', max(after) <= 16 * MiB + 4 * MiB, 'max after %.2f MiB over %d samples' % (max(after) / MiB, len(after)))
