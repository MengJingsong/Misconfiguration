#!/usr/bin/env python3
"""Unit tier analysis against B2f / B2g (B2i of the file). Usage: analyze_unit.py <unit.txt> [base|nopguard]
The thresholds are the ones made exact in B2i before the run."""
import sys, re
MiB = 1048576
path = sys.argv[1]; label = sys.argv[2] if len(sys.argv) > 2 else 'base'
def kv(s): return {k: v for k, v in re.findall(r'(\S+?)=(\S+)', s)}
L = [l.strip() for l in open(path) if l.strip()]
fails = []
def chk(name, ok, detail):
    print('RESULT', 'PASS' if ok else 'FAIL', name, detail)
    if not ok: fails.append(name)
sc = [(kv(l.split('exception=')[0]), l.split('exception=')[1].split(' capacityAfter=')[0], int(l.split('capacityAfter=')[1])) for l in L if l.startswith('N1 setCapacity')]
chk('N1 five setCapacity calls recorded', len(sc) == 5, str(len(sc)))
for d, ex, capafter in sc:
    v = int(d['v'])
    if label == 'base':
        if v == 0: chk('N1 setCapacity(0) no exception', ex == 'none', ex)
        else: chk('N1 setCapacity(%d) throws UnsupportedOperationException "not permitted as this cache is disabled"' % v, ex.startswith('java.lang.UnsupportedOperationException') and 'is not permitted as this cache is disabled' in ex, ex[:90])
    else:
        chk('N1 patched: setCapacity(%d) accepted' % v, ex == 'none', ex[:90])
    chk('N1 capacity() == 0 after setCapacity(%d)' % v, capafter == 0, str(capafter))
p = [kv(l) for l in L if l.startswith('N1 puts=')][0]
chk('N1 after 2,000,000 puts size == 0 and weightedSize == 0', p['size'] == '0' and p['weightedSize'] == '0', 'size=%s weighted=%s' % (p['size'], p['weightedSize']))
chk('N1 putIfAbsent/replace false and get null every time', p['putIfAbsentTrue'] == '0' and p['replaceTrue'] == '0' and p['getNonNull'] == '0', str({k: p[k] for k in ('putIfAbsentTrue', 'replaceTrue', 'getNonNull')}))
chk('N1 heap delta < 8 MiB and RssAnon delta < 4 MiB', abs(int(p['heapDelta'])) < 8 * MiB and abs(int(p['rssAnonDelta'])) < 4 * MiB, 'heap=%s rss=%s' % (p['heapDelta'], p['rssAnonDelta']))
w = [(kv(l.split('exception=')[0]), l.split('exception=')[1].split(' getCapacity=')[0], int(l.split('getCapacity=')[1])) for l in L if l.startswith('N2 wrapper')]
for d, ex, cap in w:
    v = int(d['v'])
    if label == 'base': chk('N2 wrapper setCapacity(%d)' % v, (ex == 'none') if v == 0 else ex.startswith('java.lang.UnsupportedOperationException'), ex[:80])
    else: chk('N2 patched wrapper setCapacity(%d) accepted' % v, ex == 'none', ex[:80])
    chk('N2 wrapper getCapacity() == 0', cap == 0, str(cap))
n3 = [kv(l) for l in L if l.startswith('N3 phase=')]
start = [kv(l) for l in L if l.startswith('N3 class=')][0]
cap0 = int(start['capacityAtStart'])
chk('N3 control is the OHC row cache at 16 MiB', start['class'] in ('InstrumentingCache', 'AutoSavingCache') and cap0 == 16 * MiB, str(start))
A = [d for d in n3 if d['phase'] == 'A']
chk('N3 phase A weightedSize <= capacity at every report', all(int(d['weightedSize']) <= int(d['capacity']) for d in A), str([d['weightedSize'] for d in A]))
chk('N3 phase A ends >= 14 MiB', int(A[-1]['weightedSize']) >= 14 * MiB, A[-1]['weightedSize'])
raise_l = [l for l in L if l.startswith('N3 setRowCacheCapacityInMB')][0]
chk('N3 setRowCacheCapacityInMB(32) succeeds, capacity 32 MiB', 'exception=none' in raise_l and 'capacityAfter=%d' % (32 * MiB) in raise_l, raise_l)
B = [d for d in n3 if d['phase'] == 'B']
chk('N3 phase B weightedSize in (16 MiB, 32 MiB]', all(16 * MiB < int(d['weightedSize']) <= 32 * MiB for d in B), str([d['weightedSize'] for d in B]))
chk('N3 RssAnon growth at end >= 80%% of weightedSize', int(B[-1]['rssAnonDelta']) >= 0.8 * int(B[-1]['weightedSize']), 'rss=%s weighted=%s' % (B[-1]['rssAnonDelta'], B[-1]['weightedSize']))
for d in A + B: print('INFO N3', d)
print('\nFAILED CHECKS (%d): %s' % (len(fails), fails))
