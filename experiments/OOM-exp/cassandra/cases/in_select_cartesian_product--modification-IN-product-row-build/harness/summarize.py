#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for a U7 run: endpoint, client steps, K (RequestsSize), U (post-GC heap rise per step
from gc.log, heap_info), memtable, MutationStage, NTR top frames, GC, direct."""
import datetime, glob, os, re, sys
R = sys.argv[1]
def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''
drv = rd('driver.txt'); out = rd('stdout.txt')
m = re.search(r'END (.*)', drv); print('endpoint:', m.group(1) if m else '?')
for l in out.splitlines():
    if 'java.lang.OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file created' in l or 'Executing /bin/sh -c' in l or 'Executing "kill' in l:
        print('stdout:', l.strip()[:220])
for l in rd('resolved.txt').splitlines(): print('resolved:', l)
fl = rd('vm-flags.txt')
for k in ('MaxHeapSize', 'MaxDirectMemorySize', 'HeapDumpOnOutOfMemoryError', 'UseG1GC', 'G1HeapRegionSize', 'AlwaysPreTouch'):
    mm = re.search(r'-XX:([+-]?)%s=?(\S*)' % k, fl)
    if mm: print('flag %s %s%s' % (k, mm.group(1), mm.group(2)))
bl = re.search(r'^(\S+) baseline done', drv, re.M)
# gc after-GC series with epoch
gc = ''.join(open(f, errors='replace').read() for f in sorted(glob.glob(os.path.join(R, 'gc.log*'))))
ev = []
for mm in re.finditer(r'^\[(\d{4}-\d\d-\d\dT[\d:.]+[-+]\d{4})\]\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\(\d+\) (Pause [^\n]*?) (\d+)M->(\d+)M\((\d+)M\) (\d+\.\d+)ms', gc, re.M):
    t = datetime.datetime.strptime(mm.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
    ev.append((t, mm.group(3), int(mm.group(4)), int(mm.group(5)), int(mm.group(6)), float(mm.group(7))))
steps = []
cur = None
for l in rd('client.txt').splitlines():
    d = dict(x.split('=', 1) for x in l.split(' ', 1)[1].split(' ') if '=' in x) if ' ' in l else {}
    if l.startswith('send '): cur = d; steps.append(d)
    elif l.startswith('end ') and cur is not None:
        cur['t_end'] = d.get('t_end'); cur['latency_ms'] = d.get('latency_ms'); cur['outcome'] = l.split('outcome=', 1)[1]
    elif l.startswith('count '): print('client:', l)
jm = [l.split(',') for l in rd('jmx.csv').splitlines()[1:] if l and l[0].isdigit()]
def col(i, t0=None, t1=None):
    o = []
    for r in jm:
        try:
            t = float(r[0])
            if (t0 is None or t >= t0) and (t1 is None or t <= t1): o.append(float(r[i]))
        except (ValueError, IndexError): pass
    return o
for i, s in enumerate(steps):
    t0 = float(s['t_send']); t1 = float(s.get('t_end') or 1e18)
    base = [e for e in ev if e[0] < t0]
    b_after = base[-1][3] if base else None
    during = [e for e in ev if t0 <= e[0] <= t1 + 5000]
    pk = max((e[3] for e in during), default=None)
    print('step %d %s p=%s q=%s k0=%s rows=%s wire_est=%s latency_ms=%s outcome=%s' % (
        i, s['kind'], s['p'], s['q'], s['k0'], s['rows'], s['wire_body_est'], s.get('latency_ms'), s.get('outcome', 'NONE (no end line)')[:200]))
    print('   GC during step %d (full %d); baseline after-GC %s MiB; max after-GC in step %s MiB; U_peak %s MiB; last after-GC %s' % (
        len(during), sum(1 for e in during if 'Full' in e[1]), b_after, pk, (pk - b_after) if (pk is not None and b_after is not None) else '-',
        ' '.join(str(e[3]) for e in during[-6:])))
    rs = col(1, t0 - 1000, t1 + 2000)
    if rs: print('   K RequestsSize max %d B; memtable max %.0f MiB; MutationStage pending max %d; NTR active max %d' % (
        max(rs), max(col(3, t0, t1 + 20000) or [0]) / 2**20, max(col(4, t0, t1 + 2000) or [0]), max(col(5, t0, t1 + 2000) or [0])))
    if s.get('t_end') and pk is not None and b_after is not None and s.get('outcome', '').startswith('OK'):
        print('   rate %.0f rows/s over latency; U/row %.1f B (post-GC rise / rows)' % (
            int(s['rows']) / max(1, int(s['latency_ms'])) * 1000, (pk - b_after) * 2**20 / int(s['rows'])))
if jm:
    rs = col(1)
    print('jmx samples %d; RequestsSize max %d; Paused max %d; direct max %.1f MiB; last row %s' % (
        len(jm), max(rs or [0]), max(col(2) or [0]), max(col(7) or [0]) / 2**20, ','.join(jm[-1])))
th = rd('threads.txt').splitlines()
tops = {}
for l in th:
    for w in l.split()[3:]:
        tops[w] = tops.get(w, 0) + 1
if th: print('thread samples %d; NTR-in-ModificationStatement top frames: %s' % (len(th), ' '.join('%s x%d' % kv for kv in sorted(tops.items(), key=lambda x: -x[1]))))
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', rd('heapinfo.txt'))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
used = [int(x) for x in re.findall(r'garbage-first heap\s+total \d+K, used (\d+)K', rd('heapinfo.txt'))]
if used: print('heap_info used max %.0f MiB' % (max(used) / 1024))
if ev:
    print('GCs %d; Pause Full %d; to-space exhausted %d; heap after GC max %d MiB of %d; first-6 after-GC %s' % (
        len(ev), sum(1 for e in ev if 'Full' in e[1]), gc.count('To-space exhausted'), max(e[3] for e in ev), ev[-1][4],
        ' '.join(str(e[3]) for e in ev[:6])))
    tend = ev[-1][0]; last = sum(e[5] for e in ev if e[0] >= tend - 60000) / 1000
    print('STW share over last 60 s of GC log: %.0f%%' % (100 * last / 60))
print('dumps:', ' '.join('%s (%d MiB)' % (os.path.basename(f), os.path.getsize(f) >> 20) for f in glob.glob(os.path.join(R, '*.hprof'))) or 'none')
