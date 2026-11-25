#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for a U16 run (from R12's): endpoint and time after full N, client ok/rf/rt/err
(abort fraction f over t = 10-60 s after full N and over the hold), latencies, R_Q, queue-full blocking, worker phases,
w (events written/s from wchar), E(t) estimate, U_h after GC, Full GCs, K_server, RssAnon, debug.log counts, drains, dumps."""
import bisect, glob, os, re, statistics, sys
from collections import Counter
R = sys.argv[1]; S = 16_000_000; EV = 2 * S + 4096
def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''
drv = rd('driver.txt'); out = rd('stdout.txt')
m = re.search(r'END (.*)', drv); print('endpoint:', m.group(1) if m else '?')
for l in out.splitlines():
    if 'java.lang.OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file created' in l or "Executing /bin/sh -c" in l:
        print('stdout:', l.strip()[:200])
cl = rd('client.txt'); t0 = re.search(r'# t0 epoch ([\d.]+)', cl); t0 = float(t0.group(1)) if t0 else None
rows = [list(map(int, l.split())) for l in cl.splitlines() if l and not l.startswith('#') and len(l.split()) == 8]
steps = [(int(a), int(b)) for a, b in re.findall(r'# step \d+ N=(\d+) established=\d+ at (\d+) ms', cl)]
for l in cl.splitlines():
    if l.startswith('#'): print('client', l)
gone = re.search(r'daemon gone while client running \(epoch ([\d.]+)\)', drv)
if steps and t0:
    lt = steps[-1][1]
    if gone: print('daemon gone %.1f s after full N (last step N=%d)' % (float(gone.group(1)) - t0 - lt / 1000, steps[-1][0]))
comp = [l.split() for l in rd('completions.txt').splitlines() if l.strip()]
def window(a_ms, b_ms):
    c = Counter(x[3].split(':')[0] if not x[3] in ('ok', 'rf', 'rt') else x[3] for x in comp if a_ms <= int(x[0]) < b_ms)
    n = c['ok'] + c['rf'] + c['rt']
    return c, (c['rf'] / n if n else float('nan'))
if steps:
    for i, (n, t) in enumerate(steps):
        t2 = steps[i + 1][1] if i + 1 < len(steps) else 10**12
        c, f = window(t, t2)
        okl = sorted(int(x[2]) for x in comp if t <= int(x[0]) < t2 and x[3] == 'ok')
        rfl = sorted(int(x[2]) for x in comp if t <= int(x[0]) < t2 and x[3] == 'rf')
        rtl = sorted(int(x[2]) for x in comp if t <= int(x[0]) < t2 and x[3] == 'rt')
        endt = max((int(x[0]) for x in comp if t <= int(x[0]) < t2), default=t)
        dur = max((endt - t) / 1000, 1e-9)
        print('step N=%d (from %d ms, %.1f s of completions): %s; f=%.3f; rate ok %.2f/s rf %.2f/s rt %.2f/s; median latency ok %s rf %s rt %s ms' % (
            n, t, dur, dict(c), f, c['ok'] / dur, c['rf'] / dur, c['rt'] / dur,
            okl[len(okl) // 2] if okl else '-', rfl[len(rfl) // 2] if rfl else '-', rtl[len(rtl) // 2] if rtl else '-'))
    lt = steps[-1][1]
    c, f = window(lt + 10000, lt + 60000)
    print('CAL window t=10-60 s after full N: %s f=%.3f' % (dict(c), f))
# amendment A-1: the coordinator's ReadTimeout fires at the same deadline as the local abort, so aborted reads reach the
# client as rt; the abort count comes from the server's logged events (qc-events.txt, UTC timestamps in debug.log).
import calendar, time as _t
qe = []
for l in rd('qc-events.txt').splitlines():
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3}) StorageProxy', l)
    if m: qe.append(calendar.timegm(_t.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S')) + int(m.group(2)) / 1000)
if steps and t0:
    lt = steps[-1][1]
    for a, b in ((10, 60), (0, 10**6)):
        na = sum(1 for e in qe if t0 + lt / 1000 + a <= e < t0 + lt / 1000 + b)
        c, f = window(lt + a * 1000, lt + b * 1000)
        n = c['ok'] + c['rf'] + c['rt']
        print('server-logged aborts t=%s-%s s after full N: %d of %d completions -> f_abort=%.3f (logged events total %d)' % (
            a, b if b < 10**6 else 'end', na, n, na / n if n else float('nan'), len(qe)))
errs = Counter(x[3][:70] for x in comp if x[3] not in ('ok', 'rf', 'rt'))
for k, v in errs.most_common(5): print('  other x%d: %s' % (v, k))
sg = rd('single.txt').strip()
if sg: print('single:'); [print('  ' + l) for l in sg.splitlines() if 'median' in l or 'rf' in l or 'rt' in l][:40]
th = [l.split() for l in rd('threads.txt').splitlines()]; th = [t for t in th if len(t) == 11]
if th:
    print('threads samples %d: max ReadStage %d, max R_Q %d (hex %d, fmt %d, concat %d), max put-blocked %d, max NTR %d' % (
        len(th), max(int(t[1]) for t in th), max(int(t[2]) for t in th), max(int(t[3]) for t in th), max(int(t[4]) for t in th),
        max(int(t[5]) for t in th), max(int(t[6]) for t in th), max(int(t[7]) for t in th)))
    print('  R_Q series:', ' '.join(t[2] for t in th))
    print('  put-blocked series:', ' '.join(t[6] for t in th))
    print('  ScheduledTasks phases:', dict(Counter(t[9] for t in th)), ' AsyncAppender-Worker:', dict(Counter(t[10] for t in th)))
    print('  AW series:', ' '.join(t[10] for t in th))
ks = re.findall(r'requestssize=(\d+)', rd('ksrv.txt')); pc = re.findall(r'paused=(\d+)', rd('ksrv.txt'))
if ks: print('K_server RequestsSize max %d (samples %d); paused max %s' % (max(map(int, ks)), len(ks), max(map(int, pc)) if pc else '-'))
dr = re.findall(r'READ(?:_REQ)?_dropped=(\d+)', rd('ksrv.txt')); ra = re.findall(r'rs_active=(\d+) rs_pending=(\d+)', rd('ksrv.txt'))
if dr: print('READ dropped max %s; ReadStage active/pending max %s/%s' % (max(map(int, dr)), max(int(a) for a, b in ra) if ra else '-', max(int(b) for a, b in ra) if ra else '-'))
hi = rd('heapinfo.txt').splitlines()
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', '\n'.join(hi))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
used = [int(x) for x in re.findall(r'garbage-first heap\s+total \d+K, used (\d+)K', '\n'.join(hi))]
if used: print('heap_info used max %.0f MiB' % (max(used) / 1024))
wc = [(float(l.split()[0]), int(m.group(1))) for l in hi for m in [re.search(r'wchar=(\d+)', l)] if m]
if len(wc) > 2 and t0:
    w0 = wc[0][1]
    rf_t = [(t0 + r[0] / 1000, r[5]) for r in rows]
    tt = [a for a, b in rf_t]
    E = []
    for ts, w in wc:
        i = bisect.bisect_right(tt, ts) - 1
        rfc = (rows[i][5] + rows[i][6]) if i >= 0 else 0   # A-1: inflow upper bound = rf + rt
        E.append((ts, rfc - (w - w0) / EV))
    rates = [((wc[i][1] - wc[i - 5][1]) / EV) / (wc[i][0] - wc[i - 5][0]) for i in range(5, len(wc)) if wc[i][0] > wc[i - 5][0]]
    print('wchar total %.0f MiB = %.1f events; w max (10 s window) %.2f events/s; E(t) estimate max %.0f, last %.0f' % (
        (wc[-1][1] - w0) / 2**20, (wc[-1][1] - w0) / EV, max(rates) if rates else 0, max(e for t, e in E), E[-1][1]))
    print('  E series (every 5th):', ' '.join('%.0f' % e for t, e in E[::5]))
gc = ''.join(open(f, errors='replace').read() for f in sorted(glob.glob(os.path.join(R, 'gc.log*'))))
hum = [(int(a), int(b)) for a, b in re.findall(r'Humongous regions: (\d+)->(\d+)', gc)]
if hum:
    after = [b for a, b in hum]; before = [a for a, b in hum]
    print('GCs %d; humongous after GC: max %d regions (%.0f MiB), median %d; before GC max %d' % (
        len(hum), max(after), max(after) * 16, statistics.median(after), max(before)))
olds = [(int(a), int(b)) for a, b in re.findall(r'Old regions: (\d+)->(\d+)', gc)]
if olds and hum:
    tot = [o[1] + h[1] for o, h in zip(olds, hum)]
    print('old+humongous after GC: max %d regions, median %d' % (max(tot), statistics.median(tot)))
pauses = [(float(x.group(1)), float(x.group(3))) for x in re.finditer(r'\[(\d+\.\d+)s\]\[[^\n]*?GC\(\d+\) (Pause [^\n]*?) (\d+\.\d+)ms', gc)]
if pauses:
    tend = pauses[-1][0]
    last = sum(p[1] for p in pauses if p[0] >= tend - 60) / 1000
    print('pauses %d; STW share over last 60 s of GC log: %.0f%%; Pause Full count %d; to-space exhausted %d' % (
        len(pauses), 100 * last / 60, gc.count('Pause Full'), gc.count('To-space exhausted')))
dl = [int(x) for x in re.findall(r'debuglog=(\d+)', '\n'.join(hi))]
if dl: print('debug.log* bytes max %.0f MiB' % (max(dl) / 2**20))
av = [int(x) for x in re.findall(r'avail=(\d+)', '\n'.join(hi))]
if av: print('/mydata avail min %.1f GiB' % (min(av) / 2**30))
print('debug counts:', rd('debugcounts.txt').replace('\n', '; '))
if rows: print('client total rf %d (logged events vs rf above)' % rows[-1][5])
d = rd('drains.txt').strip().splitlines()
if d: print('drains:', d[-1]); [print('  ' + l) for l in d[:-1][:30]]
mt = rd('montask.txt').strip()
print('monitor task line:', mt[-120:] if mt else 'none')
rid = os.path.basename(R.rstrip('/'))
dp = os.path.join(os.path.dirname(os.path.dirname(R.rstrip('/'))), 'dumps', rid + '.hprof')
print('dump:', '%s (%d MiB)' % (dp, os.path.getsize(dp) >> 20) if os.path.exists(dp) else 'none')
vf = rd('vm-flags.txt')
for k in ('MaxHeapSize', 'MaxDirectMemorySize', 'G1HeapRegionSize'):
    m = re.search(k + r'=(\d+)', vf); print('%s=%s' % (k, m.group(1) if m else '?'), end='  ')
print()
