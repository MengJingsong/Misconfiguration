#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for a U6 run (endpoint, client responses, K, parses in flight, heap after GC, GC)."""
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
for l in drv.splitlines():
    if 'baseline done' in l or 'S0 payload' in l or 'daemon gone' in l or 'client ended' in l: print('driver:', l)
print('resolved:', rd('resolved.txt').replace('\n', ' ; ')[:600])
rows = []; est_at = []; body = None
for f in sorted(glob.glob(os.path.join(R, 'client-*.txt'))):
    for l in open(f):
        if l.startswith('# established'):
            mm = re.search(r'established=(\d+) body=(\d+) at (\d+)', l); est_at.append(int(mm.group(3))); body = int(mm.group(2))
        elif not l.startswith('#') and l.strip():
            rows.append(list(map(int, l.split())))
t0 = min(est_at) if est_at else 0
if est_at: print('client: body %s B, established at %d' % (body, t0))
comp = []
for f in sorted(glob.glob(os.path.join(R, 'completions-*.txt'))):
    tag = os.path.basename(f)[12:-4]
    for l in open(f):
        if l.strip(): comp.append([tag] + l.strip().split(None, 4))
comp.sort(key=lambda c: int(c[1]))
for c in comp:
    print('  resp %s t+%.1fs conn %s latency %s ms %s' % (c[0], (int(c[1]) - t0) / 1000, c[2], c[3], ' '.join(c[4:])[:160]))
if rows: print('client outstanding max %d; K_client max %d' % (max(r[3] for r in rows), max(r[6] for r in rows)))
jm = [l.split(',') for l in rd('jmx.csv').splitlines()[1:] if l and l[0].isdigit()]
def col(i):
    o = []
    for r in jm:
        try: o.append(float(r[i]))
        except (ValueError, IndexError): pass
    return o
if jm:
    rs = col(1); pc = col(2); na = col(3); npd = col(4); du = col(5)
    print('jmx samples %d' % len(jm))
    if rs: print('K_server RequestsSize max %d; last %d' % (max(rs), rs[-1]))
    if pc: print('PausedConnections max %d' % max(pc))
    if na: print('NTR active max %d; NTR pending max %d' % (max(na), max(npd or [0])))
    if du: print('direct MemoryUsed max %.0f MiB' % (max(du) / 2**20))
    print('last jmx row:', ','.join(jm[-1]))
th = [l.split() for l in rd('threads.txt').splitlines()]
th = [t for t in th if len(t) == 7]
if th:
    print('threads samples %d: max NTR %d, lex %d, syntaxError %d, parse %d, prepare %d, measure %d' % (
        len(th), *[max(int(t[i]) for t in th) for i in range(1, 7)]))
    print('  lex series:', ' '.join(t[2] for t in th), '| last sample:', ' '.join(th[-1][1:]))
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', rd('heapinfo.txt'))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
used = [int(x) for x in re.findall(r'garbage-first heap\s+total \d+K, used (\d+)K', rd('heapinfo.txt'))]
if used: print('heap_info used max %.0f MiB' % (max(used) / 1024))
gcfiles = sorted(glob.glob(os.path.join(R, 'gc.log*')))
seen = {}
for f in gcfiles:
    for mm in re.finditer(r'\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\((\d+)\) (Pause [^\n]*?) (\d+)M->(\d+)M\(\d+M\) (\d+\.\d+)ms', open(f, errors='replace').read()):
        seen[(int(mm.group(2)), mm.group(3)[:12])] = (float(mm.group(1)), mm.group(3), int(mm.group(4)), int(mm.group(5)), float(mm.group(6)))
ev = sorted(seen.values())
if ev:
    print('GCs %d; heap after GC max %d MiB; last 8 after-GC: %s' % (len(ev), max(e[3] for e in ev), ' '.join(str(e[3]) for e in ev[-8:])))
    print('  first-10 after-GC (baseline): %s' % ' '.join(str(e[3]) for e in ev[:10]))
    full = [e for e in ev if 'Full' in e[1]]
    if full: print('  Full GCs %d: after-GC MiB %s; pause s %s' % (len(full), ' '.join(str(e[3]) for e in full[-12:]), ' '.join('%.1f' % (e[4] / 1000) for e in full[-12:])))
    tend = ev[-1][0]
    last = sum(e[4] for e in ev if e[0] >= tend - 60) / 1000
    print('pauses %d; STW share over last 60 s of GC log: %.0f%%; GC log end at uptime %.1f s' % (len(ev), 100 * last / 60, tend))
gcall = ''.join(open(f, errors='replace').read() for f in gcfiles)
print('to-space exhausted %d; humongous lines %d' % (gcall.count('To-space exhausted'), gcall.count('Humongous regions')))
cpu = rd('clientcpu.txt').splitlines()
if cpu: print('client cpu last sample:', cpu[-2][:200] if len(cpu) > 1 else cpu[-1][:200])
print('dumps:', ' '.join('%s (%d MiB)' % (os.path.basename(f), os.path.getsize(f) >> 20) for f in glob.glob(os.path.join(R, '*.hprof'))) or 'none')
