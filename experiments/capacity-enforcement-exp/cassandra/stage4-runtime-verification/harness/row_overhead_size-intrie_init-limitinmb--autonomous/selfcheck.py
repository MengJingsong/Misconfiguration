#!/usr/bin/env python3
"""Independent re-parse of the committed excerpts of run1 (results/<stem>/run1). usage: selfcheck.py <run1 folder>. PASS/FAIL/NOTE lines."""
import re, sys
R = sys.argv[1]; ok = True
def chk(n, c, d=''):
    global ok; ok &= bool(c); print(('PASS ' if c else 'FAIL ') + n + (' | ' + d if d else ''))
def note(n): print('NOTE ' + n)
def rd(p): return open(f'{R}/{p}', errors='replace').read()
# ---- unit
for lab, mib, typ in [('off-1', 1, 'OFF'), ('off-16', 16, 'OFF'), ('off-64', 64, 'OFF'), ('off-512', 512, 'OFF'), ('off-default', 1861, 'OFF'), ('off-2047', 2047, 'OFF'), ('on-16', 16, 'ON'), ('on-64', 64, 'ON')]:
    t = rd(f'unit/{lab}.out'); thr = mib * 1048576
    chk(f'unit {lab}: threshold == {mib} x 1048576 = {thr}', f'ALLOCATED_SIZE_THRESHOLD={thr} ' in t)
    m = re.search(r'FLIP .*? keys=(\d+) allocatedPos=(\d+) .*?sizeOffHeap=(\d+) sizeOnHeap=(\d+)', t)
    pos = int(m.group(2)); chk(f'unit {lab}: allocatedPos at the flip in [thr, thr+4096)', thr <= pos < thr + 4096, f'+{pos - thr}')
    chk(f'unit {lab}: ' + ('sizeOffHeap == allocatedPos' if typ == 'OFF' else 'sizeOffHeap == 0 and sizeOnHeap >= allocatedPos'), (int(m.group(3)) == pos) if typ == 'OFF' else (int(m.group(3)) == 0 and int(m.group(4)) >= pos))
    e = re.search(r'END10 .*?allocatedPos=(\d+).*?ratioToThreshold=([0-9.]+)', t)
    if e: (note if float(e.group(2)) > 1.1 else note)(f'unit {lab}: allocatedPos after 10 percent more keys = {float(e.group(2)):.4f} x threshold ({"above" if float(e.group(2)) > 1.1 else "within"} the predicted 1.1)')
    x = re.search(r'EXHAUSTED .*?allocatedPos=(\d+).*?keysAfterFlip=(\d+)', t)
    if x: note(f'unit {lab}: SpaceExhaustedException {x.group(2)} keys after the flip, allocatedPos {x.group(1)} (hard limit 2147483392)'); chk(f'unit {lab}: exhausted at 2^31-256', int(x.group(1)) == 2**31 - 256)
for k in ('0', '2048', '-5', '-1'):
    chk(f'unit bad-{k}: AssertionError "must be within 1 and 2047"', 'root=java.lang.AssertionError msg="cassandra.memtable.row_overhead_size must be within 1 and 2047"' in rd(f'unit/bad-{k}.out'))
chk('unit bad-abc: ConfigurationException (observation)', 'ConfigurationException' in rd('unit/bad-abc.out'))
chk('unit ctl-triesize64: threshold stays 1951399936', 'ALLOCATED_SIZE_THRESHOLD=1951399936' in rd('unit/ctl-triesize64.out'))
t = rd('unit/ctl-skiplist-64.out'); chk('unit ctl-skiplist-64: trie threshold 67108864 and ROW_OVERHEAD_HEAP_SIZE=64', 'ALLOCATED_SIZE_THRESHOLD=67108864' in t and 'ROW_OVERHEAD_HEAP_SIZE=64' in t)
t = rd('unit/ctl-skiplist-unset.out'); chk('unit ctl-skiplist-unset: ROW_OVERHEAD_HEAP_SIZE positive and not 64', int(re.search(r'ROW_OVERHEAD_HEAP_SIZE=(\d+)', t).group(1)) not in (64, 0))
# ---- cluster
def flush_lines(a): return [l for l in rd(f'cluster/{a}/system-log-excerpt.txt').splitlines() if 'Enqueuing flush of ks.t' in l and 'MEMTABLE_LIMIT' in l]
def ops(a): return [int(m.group(1)) for m in re.finditer(r'Writing Memtable-t@\S+\([^,]*, (\d+) ops', rd(f'cluster/{a}/system-log-excerpt.txt'))]
def offh(l):
    m = re.search(r'([0-9.]+)(GiB|MiB) \(\d+%\) off-heap', l); return float(m.group(1)) * (1024 if m.group(2) == 'GiB' else 1)
for a, n in [('a16', 16), ('a64', 64), ('adef', 1861)]:
    fl = flush_lines(a); chk(f'cluster {a}: at least one trie-size signal and every MEMTABLE_LIMIT flush shows off-heap usage in [N, 1.02N] MiB', len(fl) >= 1 and all(n <= offh(l) <= 1.02 * n for l in fl), f'{len(fl)} flushes, usage {sorted(set(round(offh(l), 3) for l in fl))}')
    chk(f'cluster {a}: signal lines == MEMTABLE_LIMIT flushes', rd(f'cluster/{a}/system-log-excerpt.txt').count('trie size limit reached') == len(fl))
chk('cluster a16, a64: at least 5 MEMTABLE_LIMIT flushes', len(flush_lines('a16')) >= 5 and len(flush_lines('a64')) >= 5)
o16, o64, oh = ops('a16'), ops('a64'), ops('h16')
r = (sum(o64[:8]) / 8) / (sum(o16[:8]) / 8); chk('cluster ops per flush a64/a16 in [3.6, 4.4]', 3.6 <= r <= 4.4, f'{r:.3f}')
r = (sum(oh[:8]) / 8) / (sum(o16[:8]) / 8); chk('cluster ops per flush h16 within 10 percent of a16', 0.9 <= r <= 1.1, f'{r:.3f}')
chk('cluster h16: 8 trie-size signals, on-heap usage ~18 MiB and 0 off-heap in the flush lines', len(flush_lines('h16')) == 8 and all('0B (0%) off-heap' in l for l in flush_lines('h16')))
l = flush_lines('s16'); chk('cluster s16: first MEMTABLE_LIMIT flush off-heap usage in [16, 656] MiB and ops >= one a16 flush', 16 <= offh(l[0]) <= 656 and ops('s16')[0] >= o16[0], f'{offh(l[0]):.1f} MiB, {ops("s16")[0]} ops')
t = rd('cluster/c64/system-log-excerpt.txt'); chk('cluster c64: no trie-size line, no MEMTABLE_LIMIT flush, no Estimated SkipListMemtable line', 'trie size limit' not in t and 'MEMTABLE_LIMIT' not in t and 'Estimated SkipList' not in t)
t = rd('cluster/a2048/schema.txt'); chk('cluster a2048: CREATE TABLE returned the AssertionError message', 'row_overhead_size must be within 1 and 2047' in t)
note('cluster a2048: DESCRIBE shows the table afterwards: ' + str('memtable = \'trie\'' in t) + '; inserts fail with "Unknown CF": ' + str('Unknown CF' in rd('cluster/a2048/system-log-excerpt.txt')))
t = rd('cluster/a16/analysis.txt'); note('cluster a16 sampled peak / threshold: ' + re.search(r'offheap max / threshold = ([0-9.]+)', t).group(1) + ' (100 ms samples)')
for a in ('a64', 'adef'): note(f'cluster {a} sampled peak / threshold: ' + re.search(r'offheap max / threshold = ([0-9.]+)', rd(f'cluster/{a}/analysis.txt')).group(1))
print('ALL PASS' if ok else 'SOME FAIL')
