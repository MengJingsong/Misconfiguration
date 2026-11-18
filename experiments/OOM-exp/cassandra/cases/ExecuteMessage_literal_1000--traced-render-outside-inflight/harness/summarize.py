#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for a B11 run (endpoint, client, R, U_h, K, RssAnon, GC)."""
import glob, os, re, statistics, sys
R = sys.argv[1]
def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''
drv = rd('driver.txt'); out = rd('stdout.txt')
m = re.search(r'END (.*)', drv); print('endpoint:', m.group(1) if m else '?')
for l in out.splitlines():
    if 'java.lang.OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file created' in l or "Executing /bin/sh -c" in l:
        print('stdout:', l.strip()[:200])
cl = rd('client.txt').splitlines()
rows = [list(map(int, l.split())) for l in cl if l and not l.startswith('#')]
for l in cl:
    if l.startswith('#'): print('client', l)
if rows:
    print('client max established %d, completed %d, errors %d, max outstanding %d, max K_client %d' % (
        max(r[2] for r in rows), rows[-1][4], rows[-1][5], max(r[3] for r in rows), max(r[6] for r in rows)))
steps = [(int(a), int(b)) for a, b in re.findall(r'# step \d+ N=(\d+) established=\d+ at (\d+) ms', rd('client.txt'))]
comp = [l.split() for l in rd('completions.txt').splitlines() if l.strip()]
ok = [c for c in comp if c[3] == 'ok']
if steps:
    ln, lt = steps[-1]
    okl = [c for c in ok if int(c[0]) >= lt]
    endt = max((int(c[0]) for c in comp), default=lt)
    print('last step N=%d started at %d ms; ok completions after it: %d; last completion line at %d ms (+%.1f s)' % (ln, lt, len(okl), endt, (endt - lt) / 1000))
    for i, (n, t) in enumerate(steps):
        t2 = steps[i + 1][1] if i + 1 < len(steps) else 10**12
        k = [c for c in ok if t <= int(c[0]) < t2]
        lat = sorted(int(c[2]) for c in k)
        print('  step N=%d: ok %d, median latency %s ms' % (n, len(k), lat[len(lat) // 2] if lat else '-'))
errs = {}
for c in comp:
    if c[3] != 'ok': errs[c[3][:60]] = errs.get(c[3][:60], 0) + 1
for k, v in sorted(errs.items(), key=lambda x: -x[1])[:6]: print('  error x%d: %s' % (v, k))
th = [l.split() for l in rd('threads.txt').splitlines()]
th = [t for t in th if len(t) == 7]
if th:
    print('threads samples %d: max NTR %d, max R(traceQuery) %d, max in hex %d, in String.<init> %d, in concat %d' % (
        len(th), max(int(t[1]) for t in th), max(int(t[2]) for t in th), max(int(t[3]) for t in th), max(int(t[4]) for t in th), max(int(t[5]) for t in th)))
    print('  R series:', ' '.join(t[2] for t in th))
ks = re.findall(r'requestssize=(\d+)', rd('ksrv.txt')); pc = re.findall(r'paused=(\d+)', rd('ksrv.txt'))
if ks: print('K_server RequestsSize max %d (samples %d) series %s; paused max %s' % (max(map(int, ks)), len(ks), ' '.join(ks), max(map(int, pc)) if pc else '-'))
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', rd('heapinfo.txt'))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
used = [int(x) for x in re.findall(r'garbage-first heap\s+total \d+K, used (\d+)K', rd('heapinfo.txt'))]
if used: print('heap_info used max %.0f MiB' % (max(used) / 1024))
gc = ''.join(open(f, errors='replace').read() for f in sorted(glob.glob(os.path.join(R, 'gc.log*'))))
hum = [(int(a), int(b)) for a, b in re.findall(r'Humongous regions: (\d+)->(\d+)', gc)]
if hum:
    after = [b for a, b in hum]; before = [a for a, b in hum]
    print('GCs %d; humongous after GC: max %d regions (%.0f MiB), median %d; before GC max %d' % (
        len(hum), max(after), max(after) * 16, statistics.median(after), max(before)))
pauses = [(float(u), m.group(0), float(ms)) for u, ms, m in
          [(x.group(1), x.group(3), x) for x in re.finditer(r'\[(\d+\.\d+)s\]\[[^\n]*?GC\(\d+\) (Pause [^\n]*?) (\d+\.\d+)ms', gc)]]
if pauses:
    tend = pauses[-1][0]
    last = sum(p[2] for p in pauses if p[0] >= tend - 60) / 1000
    print('pauses %d; STW share over last 60 s of GC log: %.0f%%; Pause Full count %d; to-space exhausted %d' % (
        len(pauses), 100 * last / 60, gc.count('Pause Full'), gc.count('To-space exhausted')))
print('dumps:', ' '.join('%s (%d MiB)' % (os.path.basename(f), os.path.getsize(f) >> 20) for f in glob.glob(os.path.join(R, '*.hprof'))) or 'none')
