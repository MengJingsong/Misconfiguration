#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for a B12 run (endpoint, client, milestone histograms, memtable, heap, GC)."""
import glob, os, re, sys
R = sys.argv[1]
def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''
drv = rd('driver.txt'); out = rd('stdout.txt')
m = re.search(r'END (.*)', drv); print('endpoint:', m.group(1) if m else '?')
for l in out.splitlines():
    if 'java.lang.OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file created' in l or 'Executing /bin/sh -c' in l or 'kill -9' in l:
        print('stdout:', l.strip()[:200])
for l in rd('client.txt').splitlines():
    if l.startswith('#'): print('client', l)
rows = [list(map(int, l.split())) for l in rd('client.txt').splitlines() if l and not l.startswith('#')]
if rows:
    r = rows[-1]; print('client last: t=%d ms issued %d ok %d err %d out %d alive %d' % tuple(r))
    # throughput over the first 60 s of samples with progress
    prog = [x for x in rows if x[2] + x[3] > 0]
    if len(prog) > 10:
        a, b = prog[0], prog[min(len(prog) - 1, 30)]
        print('rate first ~30 s: %.0f done/s' % ((b[2] + b[3] - a[2] - a[3]) * 1000 / max(1, b[0] - a[0])))
print('errcounts:', rd('errcounts.txt').strip().replace('\n', ' | ')[:400])
CL = {'S': 'org.apache.cassandra.service.paxos.PaxosState$Snapshot', 'Key': 'org.apache.cassandra.service.paxos.PaxosState$Key',
      'PS': 'org.apache.cassandra.service.paxos.PaxosState', 'DK': 'org.apache.cassandra.db.PreHashedDecoratedKey',
      'B': '[B', 'HBB': 'java.nio.HeapByteBuffer'}
def histo(n):
    t = rd(n); d = {}
    for l in t.splitlines():
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':'):
            d[p[3]] = (int(p[1]), int(p[2]))
        elif p[:1] == ['Total'] and len(p) >= 3:
            d['Total'] = (int(p[1]), int(p[2]))
    return d
mst = {}
for blk in rd('milestones.txt').split('== ')[1:]:
    tag = blk.split()[1]
    mo = re.search(r'system.paxos MemtableOnHeapDataSize (\d+)', blk); al = re.search(r'system.paxos AllMemtablesOnHeapDataSize (\d+)', blk)
    kc = re.search(r'Key Cache\s*:\s*entries (\d+)', blk)
    mst[tag] = (int(mo.group(1)) if mo else None, int(al.group(1)) if al else None, kc.group(1) if kc else '?')
drained = {}
for f in glob.glob(os.path.join(R, 'ms-*.req')):
    drained[os.path.basename(f)[3:-4]] = int(open(f).read())
tags = ['0'] + sorted([k for k in drained], key=int) + (['end'] if os.path.exists(os.path.join(R, 'histo-end.txt')) else [])
print('%-4s %7s %8s %8s %6s %8s %10s %8s %10s %10s %10s %6s' % ('ms', 'drained', 'Snapshot', 'Key', 'ACTIVE', 'DecKey', '[B MB', 'HBB', 'Total MB', 'memtOn MB', 'allMem MB', 'KCent'))
pts = []
for t in tags:
    h = histo('histo-%s.txt' % t)
    if not h: continue
    g = lambda k: h.get(CL[k], (0, 0))
    mo, al, kc = mst.get(t, (None, None, '?'))
    print('%-4s %7s %8d %8d %6d %8d %10.1f %8d %10.1f %10s %10s %6s' % (t, drained.get(t, '-'), g('S')[0], g('Key')[0], g('PS')[0], g('DK')[0],
          g('B')[1] / 1e6, g('HBB')[0], h.get('Total', (0, 0))[1] / 1e6, '%.1f' % (mo / 1e6) if mo is not None else '-', '%.1f' % (al / 1e6) if al is not None else '-', kc))
    if t != '0': pts.append((g('S')[0], h.get('Total', (0, 0))[1] - (al or 0)))
if len(pts) >= 2 and pts[-1][0] != pts[0][0]:
    print('slope (Total - allMemtablesOnHeap) per Snapshot, first->last milestone: %.0f B' % ((pts[-1][1] - pts[0][1]) / (pts[-1][0] - pts[0][0])))
met = rd('metrics.txt').strip().splitlines()
if met: print('metrics last:', met[-1])
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', rd('heapinfo.txt'))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
used = [int(x) for x in re.findall(r'garbage-first heap\s+total \d+K, used (\d+)K', rd('heapinfo.txt'))]
if used: print('heap_info used max %.0f MiB' % (max(used) / 1024))
gc = ''.join(open(f, errors='replace').read() for f in sorted(glob.glob(os.path.join(R, 'gc.log*')), key=lambda f: (f.endswith('gc.log'), f)))
aft = [int(x.group(2)) for x in re.finditer(r'GC\(\d+\) Pause [^\n]*? (\d+)M->(\d+)M\(\d+M\)', gc)]
if aft: print('GC pauses %d; heap after GC: max %d MiB, last %d MiB' % (len(aft), max(aft), aft[-1]))
pauses = [(float(u), float(ms)) for u, ms in re.findall(r'\[(\d+\.\d+)s\]\[[^\n]*?GC\(\d+\) Pause [^\n]*? (\d+\.\d+)ms', gc)]
if pauses:
    tend = pauses[-1][0]
    last = sum(p[1] for p in pauses if p[0] >= tend - 60) / 1000
    print('STW share over last 60 s of GC log: %.0f%%; Pause Full count %d' % (100 * last / 60, gc.count('Pause Full')))
print('dumps:', ' '.join('%s (%d MiB)' % (f, os.path.getsize(f) >> 20) for f in glob.glob('/dev/shm/b12-w2/%s/*.hprof' % os.path.basename(R.rstrip('/')))) or 'none')
