#!/usr/bin/env python3
"""usage: analyze.py <arm-folder> [threshold_bytes]   -> readings of one cluster arm (case B3d/B3g).
samples.csv columns: epoch_ms, direct MemoryUsed, heap used, MemtableOffHeapSize. system.log is UTC."""
import re, sys, datetime, os
d = sys.argv[1]; thr = int(sys.argv[2]) if len(sys.argv) > 2 else None
HARD = 2**31 - 256
rows = []
for l in open(d + '/samples.csv'):
    p = l.strip().split(',')
    if len(p) >= 3 and p[1].isdigit():
        rows.append((int(p[0]), int(p[1]), int(p[2]), int(p[3]) if len(p) > 3 and p[3].isdigit() else -1))
print('samples', len(rows), 'first', rows[0][0], 'last', rows[-1][0])
print('direct: start', rows[0][1], 'max', max(r[1] for r in rows), 'final', rows[-1][1])
print('heap max', max(r[2] for r in rows))
mo = [r[3] for r in rows]
print('MemtableOffHeapSize max', max(mo), 'vs hard limit', HARD, 'exceeds' if max(mo) > HARD else 'does not exceed', ' margin', HARD - max(mo))
log = open(d + '/system.log', errors='replace').read().splitlines()
def ep(l):
    m = re.search(r'(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d+)', l)
    if not m: return None
    t = datetime.datetime.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() * 1000) + int(m.group(3))
sig = [l for l in log if 'Scheduling flush due to trie size limit reached' in l]
print('trie-size flush signals:', len(sig))
for l in sig:
    t = ep(l); before = [r for r in rows if r[0] <= t]; after = [r for r in rows if r[0] > t]
    print('  signal at', t, 'sample before:', before[-1] if before else None, 'sample after:', after[0] if after else None)
fl = [l for l in log if re.search(r'Enqueuing flush of t:|Enqueuing flush of ks\.t|Flushing.*Memtable-t@|Writing Memtable-t@', l)]
print('flush lines for table t:')
for l in fl: print('  ', re.sub(r'\s+', ' ', l)[:260])
bad = [l for l in log if 'SpaceExhausted' in l or 'hard 2GB' in l or ('IllegalStateException' in l)]
print('SpaceExhausted/IllegalState lines:', len(bad)); [print('  ', b[:200]) for b in bad[:3]]
print('ERROR lines:', sum(1 for l in log if l.startswith('ERROR')))
if os.path.exists(d + '/stress.txt'):
    for l in open(d + '/stress.txt'):
        if re.match(r'(Op rate|Total partitions|Total errors|Total GC count)', l): print(l.rstrip())
ts = d + '/tablestats.txt'
if os.path.exists(ts):
    for l in open(ts):
        if re.search(r'Memtable switch count|Number of partitions|Memtable off heap|SSTable count|Space used \(live\)', l): print(l.rstrip())
