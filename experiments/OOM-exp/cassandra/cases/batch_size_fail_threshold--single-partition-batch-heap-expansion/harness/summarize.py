#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for a B14 run (endpoint, client, K, n_held, heap after GC, memtable, GC, direct)."""
import glob, os, re, sys
R = sys.argv[1]
def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''
drv = rd('driver.txt'); out = rd('stdout.txt')
m = re.search(r'END (.*)', drv); print('endpoint:', m.group(1) if m else '?')
for l in out.splitlines():
    if 'java.lang.OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file created' in l or 'Executing /bin/sh -c' in l or 'Executing "kill' in l:
        print('stdout:', l.strip()[:200])
tclient = None
for l in drv.splitlines():
    if 'baseline done' in l: print('driver:', l)
# client
rows = []; est_at = []; body = None
for f in sorted(glob.glob(os.path.join(R, 'client-p*.txt'))):
    for l in open(f):
        if l.startswith('# established'):
            mm = re.search(r'established=(\d+) body=(\d+) at (\d+)', l); est_at.append(int(mm.group(3))); body = int(mm.group(2))
        elif not l.startswith('#') and l.strip():
            rows.append(list(map(int, l.split())))
if est_at: print('client processes %d, body %s B, last established at %d' % (len(est_at), body, max(est_at)))
comp = []
for f in glob.glob(os.path.join(R, 'completions-p*.txt')):
    comp += [l.split() for l in open(f) if l.strip()]
comp.sort(key=lambda c: int(c[0]))
ok = [c for c in comp if c[3] == 'VOID']
t0 = max(est_at) if est_at else 0
print('completions VOID %d; latency median %s ms' % (len(ok), sorted(int(c[2]) for c in ok)[len(ok)//2] if ok else '-'))
errs = {}
for c in comp:
    if c[3] != 'VOID': errs[c[3][:70]] = errs.get(c[3][:70], 0) + 1
for k, v in sorted(errs.items(), key=lambda x: -x[1])[:6]: print('  status x%d: %s' % (v, k))
if ok: print('first VOID at +%.1f s, last VOID at +%.1f s after last established' % ((int(ok[0][0]) - t0) / 1000, (int(ok[-1][0]) - t0) / 1000))
# per-second outstanding summed across processes
by = {}
for r in rows: by.setdefault(r[0] // 1000, [0, 0])[0] += r[3]
if by: print('client outstanding max (sum over procs, per s) %d; K_client max %d' % (max(v[0] for v in by.values()), max(v[0] for v in by.values()) * (body or 0)))
# jmx
jm = [l.split(',') for l in rd('jmx.csv').splitlines()[1:] if l and l[0].isdigit()]
def col(i):
    o = []
    for r in jm:
        try: o.append(float(r[i]))
        except (ValueError, IndexError): pass
    return o
if jm:
    rs = col(1); pc = col(2); mt = col(3); mb = col(4); mp = col(5); na = col(6); npd = col(7); du = col(8)
    print('jmx samples %d' % len(jm))
    if rs: print('K_server RequestsSize max %d; last %d; series(MB) %s' % (max(rs), rs[-1], ' '.join('%.0f' % (x / 1e6) for x in rs)))
    if pc: print('PausedConnections max %d' % max(pc))
    if mt or mb: print('memtable heap max t %.0f MiB, big %.0f MiB' % (max(mt or [0]) / 2**20, max(mb or [0]) / 2**20))
    if mp: print('MutationStage pending max %d' % max(mp))
    if na: print('NTR active max %d; NTR pending max %d' % (max(na), max(npd or [0])))
    if du: print('direct MemoryUsed max %.0f MiB' % (max(du) / 2**20))
    print('last jmx row:', ','.join(jm[-1]))
th = [l.split() for l in rd('threads.txt').splitlines()]
th = [t for t in th if len(t) == 8]
if th:
    print('threads samples %d: max NTR %d, max held BatchMessage.execute %d, max getMutations %d, wait %d, clog %d, memt %d, decode %d' % (
        len(th), *[max(int(t[i]) for t in th) for i in range(1, 8)]))
    print('  held series:', ' '.join(t[2] for t in th), '| last sample:', ' '.join(th[-1][1:]))
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', rd('heapinfo.txt'))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
used = [int(x) for x in re.findall(r'garbage-first heap\s+total \d+K, used (\d+)K', rd('heapinfo.txt'))]
if used: print('heap_info used max %.0f MiB' % (max(used) / 1024))
gc = ''.join(open(f, errors='replace').read() for f in sorted(glob.glob(os.path.join(R, 'gc.log*'))))
aft = [(float(t), int(b), int(a)) for t, b, a in re.findall(r'\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\(\d+\) Pause [^\n]*? (\d+)M->(\d+)M\(\d+M\)', gc)]
if aft:
    print('GCs %d; heap after GC max %d MiB; last 5 after-GC: %s' % (len(aft), max(a for _, _, a in aft), ' '.join(str(a) for _, _, a in aft[-5:])))
    print('  first-10 after-GC (baseline): %s' % ' '.join(str(a) for _, _, a in aft[:10]))
    full = [(t, b, a) for (t, b, a), mm in zip(aft, re.finditer(r'\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\(\d+\) (Pause [^\n]*?) \d+M->\d+M\(\d+M\)', gc)) if 'Full' in mm.group(2)]
    if full: print('  Full GCs %d: after-GC MiB %s' % (len(full), ' '.join(str(a) for _, _, a in full)))
pauses = [(float(t), float(ms)) for t, ms in re.findall(r'\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\(\d+\) Pause [^\n]*? (\d+\.\d+)ms', gc)]
if pauses:
    tend = pauses[-1][0]
    last = sum(p[1] for p in pauses if p[0] >= tend - 60) / 1000
    print('pauses %d; STW share over last 60 s of GC log: %.0f%%; Pause Full %d; to-space exhausted %d' % (
        len(pauses), 100 * last / 60, gc.count('Pause Full'), gc.count('To-space exhausted')))
cpu = rd('clientcpu.txt').splitlines()
if cpu: print('client cpu last sample:', cpu[-2][:200] if len(cpu) > 1 else cpu[-1][:200])
print('dumps:', ' '.join('%s (%d MiB)' % (os.path.basename(f), os.path.getsize(f) >> 20) for f in glob.glob(os.path.join(R, '*.hprof'))) or 'none')
