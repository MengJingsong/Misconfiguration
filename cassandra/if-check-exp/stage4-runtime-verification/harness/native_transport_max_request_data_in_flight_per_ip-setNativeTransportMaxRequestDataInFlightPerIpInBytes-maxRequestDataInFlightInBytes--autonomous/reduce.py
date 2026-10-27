#!/usr/bin/env python3
"""B3e step 9: reduce one cluster run directory (base.csv, run.csv, nmt.txt, client.txt, times.txt, jmxset.txt) to the readings.
usage: reduce.py RUN_DIR -> key=value lines (bytes and MiB). The load window is client_start..client_end in probe time."""
import csv, re, statistics, sys, os
d = sys.argv[1]; MiB = 1048576.0
def rows(f):
    with open(os.path.join(d, f)) as fh:
        return [r for r in csv.DictReader(fh) if r.get('t_ms', '').strip().isdigit()]
def col(rs, k): return [int(r[k]) for r in rs if r[k].lstrip('-').isdigit()]
base, run = rows('base.csv'), rows('run.csv')
b_direct = statistics.median(col(base, 'direct_used'))
tm = dict(kv.split('=') for kv in open(os.path.join(d, 'times.txt')).read().split())
t_lo = int(tm['client_start_ms']) - int(tm['probe_start_ms']); t_hi = int(tm['client_end_ms']) - int(tm['probe_start_ms'])
load = [r for r in run if t_lo - 500 <= int(r['t_ms']) <= t_hi + 500]
rs = col(run, 'requests_size'); pa = col(run, 'paused'); du = col(run, 'direct_used'); hu = col(run, 'heap_used')
i_pk = max(range(len(rs)), key=lambda i: rs[i])
bi = [int(r['byip_max']) for r in run if r['byip_max'].isdigit()]
out = {
    'samples': len(run), 'baseline_samples': len(base), 'load_window_ms': t_hi - t_lo, 'load_samples': len(load),
    'baseline_requests_size_max': max(col(base, 'requests_size')), 'baseline_direct_median': int(b_direct),
    'peak_requests_size': rs[i_pk], 'peak_requests_size_t_ms': int(run[i_pk]['t_ms']),
    'peak_requests_size_MiB': round(rs[i_pk] / MiB, 3),
    'peak_requests_size_in_load': max(col(load, 'requests_size')),
    'max_paused': max(pa),
    'peak_direct_used': max(du), 'peak_delta_direct': max(du) - int(b_direct),
    'peak_delta_direct_MiB': round((max(du) - b_direct) / MiB, 1),
    'last_delta_direct_MiB': round((du[-1] - b_direct) / MiB, 1),
    'peak_heap_MiB': round(max(hu) / MiB, 1), 'last_requests_size': rs[-1],
    'samples_with_requests_size_gt0': sum(1 for x in rs if x > 0),
    'byip_max_peak': max(bi) if bi else 'NA',
}
try:
    vals = [int(m.group(1)) for m in re.finditer(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', open(os.path.join(d, 'nmt.txt')).read())]
    nb = [int(m.group(1)) for m in re.finditer(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', open(os.path.join(d, 'nmt-base.txt')).read())]
    if vals and nb:
        out.update({'nmt_other_samples': len(vals), 'nmt_other_base_MiB': round(nb[0] / 1024, 1),
                    'nmt_other_peak_over_base_MiB': round((max(vals) - nb[0]) / 1024, 1)})
except FileNotFoundError:
    pass
try:
    for l in open(os.path.join(d, 'client.txt')):
        if l.startswith('RESULT'):
            out['client'] = l.strip()
            m = re.search(r"'ok': (\d+)", l); out['ok'] = int(m.group(1)) if m else 0
            out['client_errors'] = sum(int(x) for x in re.findall(r"'(?:err|connect_err):\w+': (\d+)", l))
except FileNotFoundError:
    pass
try:                                    # r9: the JMX set
    js = open(os.path.join(d, 'jmxset.txt')).read()
    m = re.search(r'after=(\d+) t=(\d+)', js)
    if m:
        t_set = int(m.group(2)) - int(tm['probe_start_ms']); out['jmx_after'] = int(m.group(1)); out['jmx_set_t_ms'] = t_set
        pre = [int(r['requests_size']) for r in run if int(r['t_ms']) <= t_set]
        post60 = [int(r['requests_size']) for r in run if t_set + 60000 <= int(r['t_ms']) <= t_hi]
        out['jmx_peak_before_set'] = max(pre); out['jmx_samples_after_60s_in_load'] = len(post60)
        out['jmx_max_after_60s_in_load'] = max(post60) if post60 else 'NA'
except FileNotFoundError:
    pass
for k, v in out.items():
    print('%s=%s' % (k, v))
