#!/usr/bin/env python3
"""B3e step 9: reduce one cluster run directory (base.csv, run.csv, nmt.txt, client.txt, times.txt) to the readings.
usage: reduce.py RUN_DIR   -> prints key=value lines (bytes and MiB)."""
import csv, re, statistics, sys, os
d = sys.argv[1]
MiB = 1048576.0
def rows(f):
    with open(os.path.join(d, f)) as fh:
        return [r for r in csv.DictReader(fh) if r.get('t_ms', '').strip().isdigit()]
base, run = rows('base.csv'), rows('run.csv')
def col(rs, k): return [int(r[k]) for r in rs]
b_direct = statistics.median(col(base, 'direct_used'))
rs = col(run, 'requests_size'); pa = col(run, 'paused'); du = col(run, 'direct_used'); hu = col(run, 'heap_used')
i_pk = max(range(len(rs)), key=lambda i: rs[i])
out = {
    'samples': len(run), 'baseline_samples': len(base),
    'baseline_requests_size_max': max(col(base, 'requests_size')),
    'baseline_direct_median': int(b_direct),
    'peak_requests_size': rs[i_pk], 'peak_requests_size_t_ms': int(run[i_pk]['t_ms']),
    'peak_requests_size_MiB': round(rs[i_pk] / MiB, 3),
    'max_paused': max(pa),
    'peak_direct_used': max(du), 'peak_delta_direct': max(du) - int(b_direct),
    'peak_delta_direct_MiB': round((max(du) - b_direct) / MiB, 1),
    'last_delta_direct_MiB': round((du[-1] - b_direct) / MiB, 1),
    'peak_heap_MiB': round(max(hu) / MiB, 1),
    'last_requests_size': rs[-1],
    'samples_with_requests_size_gt0': sum(1 for x in rs if x > 0),
}
# NMT "Other" committed (KB), peak minus first sample
try:
    vals = [int(m.group(1)) for m in re.finditer(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', open(os.path.join(d, 'nmt.txt')).read())]
    if vals:
        out.update({'nmt_other_samples': len(vals), 'nmt_other_first_MiB': round(vals[0] / 1024, 1),
                    'nmt_other_peak_delta_MiB': round((max(vals) - vals[0]) / 1024, 1)})
except FileNotFoundError:
    pass
try:
    nb = [int(m.group(1)) for m in re.finditer(r'Other \(reserved=\d+KB, committed=(\d+)KB\)', open(os.path.join(d, 'nmt-base.txt')).read())]
    if nb and 'nmt_other_samples' in out:
        out['nmt_other_base_MiB'] = round(nb[0] / 1024, 1)
        out['nmt_other_peak_over_base_MiB'] = round((max(vals) - nb[0]) / 1024, 1)
except FileNotFoundError:
    pass
try:
    for l in open(os.path.join(d, 'client.txt')):
        if l.startswith('RESULT'):
            out['client'] = l.strip()
            m = re.search(r"'ok': (\d+), 'overloaded': (\d+), 'other_err': (\d+)", l)
            if m: out.update({'ok': int(m.group(1)), 'overloaded': int(m.group(2)), 'other_err': int(m.group(3))})
except FileNotFoundError:
    pass
for k, v in out.items():
    print('%s=%s' % (k, v))
