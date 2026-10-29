#!/usr/bin/env python3
"""usage: analyze.py <arm-folder> [threshold_MiB]   -> readings of one cluster arm (case B3d/B3g).
samples.csv columns (100 ms): epoch_ms, direct MemoryUsed, heap used, MemtableOffHeapSize, MemtableOnHeapSize.  system.log is UTC."""
import re, sys, datetime, os
d = sys.argv[1]; thr = int(sys.argv[2]) * 1048576 if len(sys.argv) > 2 else None
rows = []
for l in open(d + '/samples.csv'):
    p = l.strip().split(',')
    if len(p) >= 5 and p[1].isdigit():
        rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3]) if p[3].lstrip('-').isdigit() else -1, int(p[4]) if p[4].lstrip('-').isdigit() else -1))
print('samples', len(rows), 'interval ms (median)', sorted(rows[i+1][0]-rows[i][0] for i in range(len(rows)-1))[len(rows)//2] if len(rows) > 2 else '-')
print('MemtableOffHeapSize max', max(r[3] for r in rows), ' MemtableOnHeapSize max', max(r[4] for r in rows), ' heap max', max(r[2] for r in rows), ' direct max', max(r[1] for r in rows))
if thr: print('threshold bytes', thr, ' offheap max / threshold = %.4f' % (max(r[3] for r in rows) / thr), ' onheap max / threshold = %.4f' % (max(r[4] for r in rows) / thr))
log = open(d + '/system.log', errors='replace').read().splitlines()
def ep(l):
    m = re.search(r'(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d+)', l)
    if not m: return None
    t = datetime.datetime.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() * 1000) + int(m.group(3))
sig = [l for l in log if 'Scheduling flush due to trie size limit reached' in l]
print('trie-size flush signals:', len(sig))
before_vals = []
for l in sig:
    t = ep(l); b = [r for r in rows if r[0] <= t]; a = [r for r in rows if r[0] > t]
    if b:
        before_vals.append(max(x[3] for x in b[-3:]))
        print('  signal at', t, 'last samples before (offheap, onheap):', [(x[3], x[4]) for x in b[-3:]], 'first after:', (a[0][3], a[0][4]) if a else None)
if thr and before_vals: print('  peak metric just before each signal / threshold:', ['%.4f' % (v / thr) for v in before_vals])
enq = [l for l in log if re.search(r'Enqueuing flush of ks\.t', l)]
wr = [l for l in log if re.search(r'Writing Memtable-t@', l)]
print('flushes enqueued for ks.t:', len(enq))
for l in enq: print('  ', re.sub(r'\s+', ' ', l)[30:230])
ops = []
for l in wr:
    m = re.search(r'\((\S+) serialized bytes, (\d+) ops, (\S+) \((\d+)%\) on-heap, (\S+) \((\d+)%\) off-heap', l)
    if m: ops.append(int(m.group(2))); print('   writing:', m.group(2), 'ops, on-heap', m.group(3), 'off-heap', m.group(5))
ml = [l for l in enq if 'MEMTABLE_LIMIT' in l]
print('MEMTABLE_LIMIT flushes:', len(ml), ' ops of each Writing line:', ops)
print('"Estimated SkipListMemtable row overhead" lines:', sum(1 for l in log if 'Estimated SkipListMemtable row overhead' in l))
bad = [l for l in log if 'AssertionError' in l or 'ExceptionInInitializerError' in l or 'NoClassDefFoundError' in l or 'SpaceExhausted' in l]
print('AssertionError/ExceptionInInitializer/NoClassDefFound/SpaceExhausted lines in system.log:', len(bad)); [print('  ', b[:220]) for b in bad[:4]]
print('ERROR lines:', sum(1 for l in log if l.startswith('ERROR')))
if os.path.exists(d + '/stress.txt'):
    for l in open(d + '/stress.txt'):
        if re.match(r'(Op rate|Total partitions|Total errors|Total GC count)', l): print(l.rstrip())
ts = d + '/tablestats.txt'
if os.path.exists(ts):
    for l in open(ts):
        if re.search(r'Memtable switch count|Number of partitions|Memtable off heap|Memtable data size|SSTable count|Space used \(live\)', l): print(l.rstrip())
