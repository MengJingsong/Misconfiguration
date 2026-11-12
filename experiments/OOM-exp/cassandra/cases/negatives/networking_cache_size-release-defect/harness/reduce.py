#!/usr/bin/env python3
"""B1 reduce: usage reduce.py <readings.csv> [requests_per_cycle]
readings.csv rows: epoch,tag,nmt_other_KB,rss_KB,t_ms,capacity,size,used,overflow,pooled,misses,direct_used,direct_count,requests_size,heap_used,clients
Prints per post-GC reading the deltas from c0-post (MiB): chunks reserved (size-overflow), slots in use (used-overflow),
OverflowSize, java.nio direct, NMT Other, RSS, RequestsSize; plus the pre-GC direct delta."""
import sys
rows = {}
for line in open(sys.argv[1]):
    f = line.strip().split(',')
    if len(f) < 16 or f[4] == 'ERR':
        continue
    tag = f[1]
    v = dict(nmt=float(f[2]) * 1024 if f[2] != 'NA' else float('nan'), rss=float(f[3]) * 1024,
             size=int(f[6]), used=int(f[7]), ovf=int(f[8]), misses=int(f[10]), direct=int(f[11]),
             req=int(f[13]), heap=int(f[14]),
             tot=float(f[16]) * 1024 if len(f) > 16 and f[16] != 'NA' else float('nan'))
    v['chunks'] = v['size'] - v['ovf']
    v['slots'] = v['used'] - v['ovf']
    rows[tag] = v
M = 1048576.0
b = rows['c0-post']
print('%-6s %9s %9s %10s %9s %9s %9s %7s %10s %8s' % ('cycle', 'chunks', 'slots', 'Overflow', 'direct', 'NMTother', 'RSS', 'ReqSz', 'preGCdir', 'misses') + '  NMTtotal')
k = 0
while ('c%d-post' % k) in rows:
    p = rows['c%d-post' % k]
    q = rows.get('c%d-pre' % k, p)
    print('%-6s %9.1f %9.1f %10.1f %9.1f %9.1f %9.1f %7d %10.1f %8d' % (
        'c%d' % k, (p['chunks'] - b['chunks']) / M, (p['slots'] - b['slots']) / M, (p['ovf'] - b['ovf']) / M,
        (p['direct'] - b['direct']) / M, (p['nmt'] - b['nmt']) / M, (p['rss'] - b['rss']) / M, p['req'],
        (q['direct'] - b['direct']) / M, p['misses'] - b['misses']) + '  %8.1f' % ((p['tot'] - b['tot']) / M))
    k += 1
