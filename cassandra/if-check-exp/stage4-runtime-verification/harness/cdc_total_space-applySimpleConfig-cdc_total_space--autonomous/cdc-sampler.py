#!/usr/bin/env python3
"""Samples cdc_raw every <interval> s until <stopfile> is removed (case B3d as amended 2026-10-24).
usage: cdc-sampler.py <cdc_raw dir> <out prefix> <interval s> <stopfile>
<prefix>.csv    ts_ms,dir_exists,links,link_bytes,link_alloc_bytes,idx,idx_bytes,gap_ms
                (links = CommitLog-*.log files, apparent bytes = st_size, allocated = st_blocks*512; idx = *_cdc.idx)
<prefix>.events ts_ms +|- name size      (a name that appears or disappears)
"""
import os, sys, time
d, pre, iv, stop = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
csv = open(pre + '.csv', 'w'); ev = open(pre + '.events', 'w')
csv.write('ts_ms,dir_exists,links,link_bytes,link_alloc_bytes,idx,idx_bytes,gap_ms\n')
prev = {}; last = None
while os.path.exists(stop):
    t = int(time.time() * 1000)
    cur = {}; links = lb = la = idx = ib = 0; ex = int(os.path.isdir(d))
    if ex:
        try:
            names = os.listdir(d)
        except OSError:
            names = []
        for n in names:
            try:
                st = os.stat(os.path.join(d, n))
            except OSError:
                continue
            if n.startswith('CommitLog-') and n.endswith('.log'):
                links += 1; lb += st.st_size; la += st.st_blocks * 512; cur[n] = st.st_size
            elif n.endswith('_cdc.idx'):
                idx += 1; ib += st.st_size
    for n in cur:
        if n not in prev:
            ev.write('%d + %s %d\n' % (t, n, cur[n]))
    for n in prev:
        if n not in cur:
            ev.write('%d - %s %d\n' % (t, n, prev[n]))
    prev = cur
    csv.write('%d,%d,%d,%d,%d,%d,%d,%d\n' % (t, ex, links, lb, la, idx, ib, 0 if last is None else t - last))
    csv.flush(); ev.flush(); last = t
    time.sleep(iv)
