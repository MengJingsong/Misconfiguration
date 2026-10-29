#!/usr/bin/env python3
"""usage: analyze_cluster.py <run dir>   parses wcs.txt, readings.txt, heap.csv, components-*.txt of one run; prints ANALYSIS lines (flush window and rebuild window)."""
import re, sys, os
d = sys.argv[1]
rd = dict(l.split(' ', 1) for l in open(d + '/readings.txt').read().splitlines() if ' ' in l)
fl0, fl1, rb0, rb1 = (int(rd[k].split()[0]) for k in ('FLUSH_START_MS', 'FLUSH_END_MS', 'REBUILD_START_MS', 'REBUILD_END_MS'))
ev = []
stack = {}
for l in open(d + '/wcs.txt'):
    kv = dict(re.findall(r'(\w+)=(\S+)', l))
    th = kv['thread']
    if l.startswith('WCS_ENTER'): stack[th] = (int(kv['t']), int(kv['alloc']), int(kv['M']))
    elif l.startswith('WCS_EXIT'):
        t0, a0, m = stack.pop(th)
        ev.append(dict(t0=t0, t1=int(kv['t']), alloc=int(kv['alloc']) - a0, M=m, **{k: kv.get(k) for k in ('num_leaves', 'num_values', 'treeLen', 'postLen', 'max_points_in_leaf_node', 'bytes_per_value')}, bpv=kv.get('bytes_per_value')))
heap = [tuple(map(int, l.split(','))) for l in open(d + '/heap.csv').read().splitlines()[1:] if l.split(',')[1] != '-1']
def window(name, a, b, bpv=None):
    if name == 'flush': a = 0   # the load triggers automatic memtable flushes (up to 88 sstables): the flush phase is everything before the rebuild
    w = [e for e in ev if a - 2000 <= e['t0'] <= b + 2000 and (bpv is None or e['bpv'] == bpv)]
    h = [x[1] for x in heap if a <= x[0] <= b + 2000]
    print('ANALYSIS %s bpv=%s segments=%d allocSum=%d allocMax=%d leavesSum=%d valuesSum=%d treeLenSum=%d postLenSum=%d maxLeavesOneSegment=%d M=%s heapUsedPeak_kB=%d heapSamples=%d' % (
        name, bpv, len(w), sum(e['alloc'] for e in w), max([e['alloc'] for e in w] or [0]), sum(int(e['num_leaves'] or 0) for e in w), sum(int(e['num_values'] or 0) for e in w),
        sum(int(e['treeLen'] or 0) for e in w), sum(int(e['postLen'] or 0) for e in w), max([int(e['num_leaves'] or 0) for e in w] or [0]), sorted(set(e['M'] for e in w)), max(h or [0]), len(h)))
for b in (None, '8', '24'):
    window('flush', fl0, fl1, b); window('rebuild', rb0, rb1, b)
print('ANALYSIS heapUsedPeak_all_kB=%d' % max(x[1] for x in heap))
for k in ('LOAD_SECONDS', 'AUTO_FLUSHES_DURING_LOAD', 'TOO_MANY_NODES_LINES'): print('ANALYSIS %s %s' % (k, rd.get(k)))
for f in ('components-after-flush.txt', 'components-after-rebuild.txt'):
    bt = sum(int(l.split()[0]) for l in open(d + '/' + f) if 'BalancedTree' in l); pl = sum(int(l.split()[0]) for l in open(d + '/' + f) if 'PostingLists' in l)
    print('ANALYSIS %s BalancedTreeBytes=%d PostingListsBytes=%d' % (f, bt, pl))
