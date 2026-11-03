#!/usr/bin/env python3
"""Samples the commit-log directory every <interval> s until <stopfile> is removed (case B3d as amended 2026-10-25).
Adapted from harness/cdc_total_space-applySimpleConfig-cdc_total_space--autonomous/cdc-sampler.py.
usage: seg-sampler.py <commitlog dir> <out prefix> <interval s> <stopfile>
<prefix>.csv    ts_ms,files,apparent_bytes,alloc_bytes,min_size,max_size,n_not_S,gap_ms      (S given by env SEG_S, bytes)
<prefix>.files  ts_ms name st_size alloc_bytes      (one line per file per sample)
<prefix>.events ts_ms +|- name size                 (a name that appears or disappears)
"""
import os, sys, time
d, pre, iv, stop = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
S = int(os.environ['SEG_S'])
csv = open(pre + '.csv', 'w'); fl = open(pre + '.files', 'w'); ev = open(pre + '.events', 'w')
csv.write('ts_ms,files,apparent_bytes,alloc_bytes,min_size,max_size,n_not_S,gap_ms\n')
prev = {}; last = None
while os.path.exists(stop):
    t = int(time.time() * 1000)
    cur = {}; ab = al = 0; mn = mx = -1; nn = 0
    try:
        names = os.listdir(d)
    except OSError:
        names = []
    for n in sorted(names):
        if not (n.startswith('CommitLog-') and n.endswith('.log')):
            continue
        try:
            st = os.stat(os.path.join(d, n))
        except OSError:
            continue
        cur[n] = st.st_size; ab += st.st_size; al += st.st_blocks * 512
        mn = st.st_size if mn < 0 else min(mn, st.st_size); mx = max(mx, st.st_size)
        if st.st_size != S:
            nn += 1
        fl.write('%d %s %d %d\n' % (t, n, st.st_size, st.st_blocks * 512))
    for n in cur:
        if n not in prev:
            ev.write('%d + %s %d\n' % (t, n, cur[n]))
    for n in prev:
        if n not in cur:
            ev.write('%d - %s %d\n' % (t, n, prev[n]))
    prev = cur
    csv.write('%d,%d,%d,%d,%d,%d,%d,%d\n' % (t, len(cur), ab, al, mn, mx, nn, 0 if last is None else t - last))
    csv.flush(); fl.flush(); ev.flush(); last = t
    time.sleep(iv)
