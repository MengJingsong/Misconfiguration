#!/usr/bin/env python3
"""Per-run numbers for the cluster tier (B3i.3): window from B's system.log, baseline = median of the 5 s before the window,
P = max(direct_used in window) - baseline. Usage: analyze_cluster.py <run dir> [<run dir> ...]   -> prints one JSON line per run."""
import sys, os, re, json, statistics, calendar, time
def ts(line):
    m = re.search(r'(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d{3})', line)
    if not m:
        return None
    return calendar.timegm(time.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S')) * 1000 + int(m.group(3))
def analyse(d):
    r = {'run': os.path.basename(d.rstrip('/'))}
    s = json.load(open(d + '/summary.json'))
    r.update({k: s.get(k) for k in ['chunk_kb', 'ratio', 'mode', 'B_outcome', 'B_data_bytes']})
    t0 = t1 = None
    for line in open(d + '/B-system.log', errors='replace'):
        if t0 is None and 'Executing streaming plan for Bootstrap' in line:
            t0 = ts(line)
        if 'All sessions completed' in line:
            t1 = ts(line)
    r['window_ms'] = [t0, t1]
    S = []
    for line in open(d + '/samples.csv'):
        p = line.strip().split(',')
        if p[0].isdigit():
            S.append((int(p[0]), int(p[1]), int(p[2])))
    r['n_samples'] = len(S)
    if t0 is None:
        r['error'] = 'no stream window'; return r
    if t1 is None:
        t1 = t0 + 120000  # failed stream: use the first 120 s
        r['window_open_ended'] = True
    base = [u for (t, u, c) in S if t0 - 5000 <= t < t0]
    win = [(t, u, c) for (t, u, c) in S if t0 <= t <= t1 + 500]
    r['baseline_median'] = statistics.median(base) if base else None
    r['baseline_n'] = len(base)
    if base and win:
        pk = max(win, key=lambda x: x[1])
        r['peak_in_window'] = pk[1]
        r['peak_t_rel_ms'] = pk[0] - t0
        r['P_bytes'] = pk[1] - r['baseline_median']
        r['P_MiB'] = round(r['P_bytes'] / 1048576, 3)
        r['window_len_ms'] = t1 - t0
        r['samples_in_window'] = len(win)
        r['count_max_in_window'] = max(c for (_, _, c) in win)
    r['max_all'] = max(u for (_, u, _) in S) if S else None
    return r
for d in sys.argv[1:]:
    print(json.dumps(analyse(d)))
