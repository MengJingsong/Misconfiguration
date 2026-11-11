#!/usr/bin/env python3
"""Readings table of the cluster tier (B3d, as amended 2026-10-26) of page_size_fail_threshold-execute-pageSize--autonomous.

usage: summarize.py <cluster log dir>   -> prints one line per query and writes <dir>/readings.txt

Per QUERY line of summary.txt: heap baseline = median of heap.tsv samples in [pre_ms, probe_start_ms) (the 2 s before the probe);
peak = max sample in [probe_start_ms, post_end_ms]; delta = peak - baseline. Humongous: the largest "Humongous regions: a->b" `a`
of a GC in gc.log inside [probe_start_ms, post_end_ms] (16 MiB regions), and the number of GCs there."""
import datetime, re, statistics, sys

d = sys.argv[1]
heap = []
for ln in open(d + '/heap.tsv'):
    if ln.startswith('#'):
        continue
    p = ln.split()
    heap.append((int(p[0]), int(p[1])))

gcev = []  # (epoch_ms, kind, value)
tre = re.compile(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d{4})\]')
try:
    for ln in open(d + '/gc.log', errors='replace'):
        m = tre.match(ln)
        if not m:
            continue
        t = int(datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000)
        h = re.search(r'Humongous regions: (\d+)->(\d+)', ln)
        if h:
            gcev.append((t, 'hum', int(h.group(1))))
        if re.search(r'GC\(\d+\) Pause ', ln) and 'M->' in ln:
            gcev.append((t, 'pause', 1))
except FileNotFoundError:
    pass

MiB = 1024 * 1024
out = []
for ln in open(d + '/summary.txt'):
    if not ln.startswith('QUERY '):
        continue
    tag = ln.split()[1]
    g = dict(re.findall(r'(\w+)=(\S+)', ln))
    m0, m1, m2, m3 = (int(g[k]) for k in ('pre_ms', 'probe_start_ms', 'probe_end_ms', 'post_end_ms'))
    pre = [u for t, u in heap if m0 <= t < m1]
    win = [u for t, u in heap if m1 <= t <= m3]
    base = statistics.median(pre) if pre else float('nan')
    peak = max(win) if win else float('nan')
    hum = [v for t, k, v in gcev if k == 'hum' and m1 <= t <= m3]
    npause = sum(1 for t, k, v in gcev if k == 'pause' and m1 <= t <= m3)
    rr = re.search(r'rowsread_before=count=(\d+) rowsread_after=count=(\d+)', ln)
    drr = int(rr.group(2)) - int(rr.group(1)) if rr else None
    s = ('%-18s outcome=%-5s rows=%-6s has_more=%-5s pw=%s rowsreadD=%s heap_base=%.1fMiB peak=%.1fMiB delta=%.1fMiB '
         'n_pre=%d n_win=%d gcs=%d hum_max=%s err=%s' % (
             tag, g.get('outcome'), g.get('rows'), g.get('has_more'), g.get('page_size_warnings'), drr,
             base / MiB, peak / MiB, (peak - base) / MiB, len(pre), len(win), npause, max(hum) if hum else '-',
             (re.search(r'err=\[(.*?)\] \|', ln).group(1)[:110] if 'err=[' in ln else '')))
    out.append(s)
open(d + '/readings.txt', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
