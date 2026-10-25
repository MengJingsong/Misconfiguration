#!/usr/bin/env python3
"""Unit-tier analyzer: python3 analyze_unit.py <unit.txt>. Prints PASS/FAIL per B2f prediction."""
import sys, re
MAXI = 2**31 - 1; W = 1024; fails = 0
def kv(line): return dict(re.findall(r'(\w+)=(\S+)', line))
def chk(name, ok, detail=''):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else '')); fails += (not ok)
L = open(sys.argv[1]).read().splitlines()
for l in L:
    if l.startswith('fill '):
        d = kv(l); C = int(d['cap']); n = C // W
        s = int(d['size_settled']); ws = int(d['weightedSize_settled']); mx = int(d['maxWeightedSizeSeenDuringPuts'])
        tag = 'fill cap=%dMiB threads=%s' % (C >> 20, d['threads'])
        chk(tag + ': settled weightedSize <= C', ws <= C, 'weightedSize=%d C=%d' % (ws, C))
        chk(tag + ': size = C/1KiB within 1%', abs(s - n) <= 0.01 * n, 'size=%d expected=%d' % (s, n))
        chk(tag + ': max weightedSize seen during puts <= C + 1 entry', mx <= C + W, 'max=%d' % mx)
        chk(tag + ': immediate weightedSize <= C + 1 entry', int(d['weightedSize_immediate']) <= C + W)
    elif l.startswith('shrink before'):
        d = kv(l); chk('shrink: before, weightedSize == 64MiB', int(d['weightedSize']) == 64 << 20)
    elif l.startswith('shrink after'):
        d = kv(l); chk('shrink: capacity now 8MiB and settled weightedSize <= 8MiB', int(d['capacity']) == 8 << 20 and int(d['weightedSize_settled']) <= 8 << 20, 'weightedSize=%s size=%s' % (d['weightedSize_settled'], d['size_settled']))
    elif l.startswith('guard ') and 'sum=' in l:
        d = kv(l); label = l.split()[1]; s = int(d['sum']); ex = l.split('exception=')[1].split(' present=')[0]
        if s > MAXI:
            chk('guard %s: sum %d > MAX throws IllegalArgumentException with the filed message' % (label, s), ex == 'java.lang.IllegalArgumentException:Serialized size cannot be more than 2GiB/Integer.MAX_VALUE' and d['present'] == 'false')
        else:
            chk('guard %s: sum %d <= MAX does not throw' % (label, s), ex == 'none', 'present=%s (evicted at once: weight > capacity 64MiB)' % d['present'])
    elif l.startswith('guard after_rejects'):
        d = kv(l); chk('guard: cache usable after rejected puts', d['get_ok'] == 'true')
    elif l.startswith('control weight0'):
        d = kv(l); chk('control weight 0: never evicts by weight (size == puts, weightedSize 0)', d['weightedSize'] == '0' and d['size'] == '100000')
    elif l.startswith('control constweigher1'):
        d = kv(l); chk('control constant weigher 1: caps entry count (size == capacity), not bytes', d['size'] == d['capacity'] == '1000' or int(d['size']) <= 1000)
    elif l.startswith('real '):
        d = kv(l); print('INFO real classes:', l)
        chk('real classes: weight = KeyCacheKey + RowIndexEntry and weightedSize <= C', int(d['sum']) == int(d['KeyCacheKey_unsharedHeapSize']) + int(d['RowIndexEntry_unsharedHeapSize']) and int(d['weightedSize']) <= int(d['capacity']))
print('TOTAL FAIL:', fails); sys.exit(1 if fails else 0)
