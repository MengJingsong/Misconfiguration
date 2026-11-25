#!/usr/bin/env python3
"""B28 summarize.py <run dir>: endpoint, time to endpoint after full N, requests/s, latency median, errors, max K_q
(TracingStage PendingTasks), dropped _TRACE, consumer rate, max K (RequestsSize), U_h (humongous regions after GC x 16 MiB)
max/median, heap after GC, memtable trace bytes max, STW share over the last 60 s of the GC log, Full GCs, max RssAnon,
dumps. Ramp runs: per step requests/s and PendingTasks slope."""
import glob, os, re, sys, statistics as stt, datetime as dt
R = sys.argv[1]


def rd(n):
    try: return open(os.path.join(R, n), errors='replace').read()
    except OSError: return ''


drv = rd('driver.txt'); out = rd('stdout.txt')
m = re.search(r'END (.*)', drv); print('endpoint:', m.group(1) if m else '?')
print('run:', (re.search(r'run \S+ .*', drv) or re.search('.*', drv)).group(0))
for l in out.splitlines():
    if 'java.lang.OutOfMemoryError' in l or 'Dumping heap' in l or 'Heap dump file created' in l or 'Executing /bin/sh -c' in l or 'kill -9' in l:
        print('stdout:', l.strip()[:200])
for l in drv.splitlines():
    if 'S0 ' in l or 'load start' in l or 'daemon gone' in l or 'client ended' in l or 'OOM line seen' in l or 'DISK' in l:
        print('driver:', l[:400])
print('resolved:', rd('resolved.txt').replace('\n', ' ; ')[:900])


def dts(pat):
    mm = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)([-+]\d{4}) ' + pat, drv)
    if not mm: return None
    return dt.datetime.strptime(mm.group(1) + mm.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()


t_oom = dts('OOM line seen'); t_gone = dts('daemon gone'); t_hold = dts('client ended')
cl = rd('client-p0.txt')
mt0 = re.search(r't0=(\d+)', cl); steps = [(int(a), int(b), int(c)) for a, b, c in re.findall(r'# step (\d+) N=(\d+) at (\d+)', cl)]
t0 = int(mt0.group(1)) / 1000 if mt0 else None
t_full = steps[-1][2] / 1000 if steps else t0
comp = []
for l in rd('completions-p0.txt').splitlines():
    p = l.split(None, 3)
    if len(p) >= 3: comp.append((int(p[0]) / 1000, p[1], int(p[2]), p[3] if len(p) > 3 else ''))
ok = [c for c in comp if c[3].startswith('op8')]
errs = [c for c in comp if not c[3].startswith('op8')]
if t0:
    t_end = t_oom or t_gone or t_hold or (comp[-1][0] if comp else t0)
    span = max(t_end - t0, 1e-3)
    print('load: t0 %s; full N at +%.0f s; end %s at +%.1f s (%.1f s after full N)' % (
        dt.datetime.fromtimestamp(t0).strftime('%H:%M:%S'), t_full - t0,
        'OOM' if t_oom else ('daemon-gone' if t_gone else 'hold'), t_end - t0, t_end - t_full))
    lat = [c[2] for c in ok]
    print('responses ok %d, errors %d; requests/s overall %.2f; latency median %s ms p90 %s ms max %s ms' % (
        len(ok), len(errs), len(ok) / span, int(stt.median(lat)) if lat else '-',
        sorted(lat)[int(0.9 * (len(lat) - 1))] if lat else '-', max(lat) if lat else '-'))
    for c in errs[:5]: print('  error:', c[1], c[2], c[3][:160])
jm = [l.split(',') for l in rd('jmx.csv').splitlines()[1:] if l and l[0].isdigit()]


def col(rows, i):
    o = []
    for r in rows:
        try: o.append((int(r[0]) / 1000, float(r[i])))
        except (ValueError, IndexError): pass
    return o


if jm:
    pend = col(jm, 1); compl = col(jm, 2); drop = col(jm, 4); mut = col(jm, 5); rs = col(jm, 6); hu = col(jm, 7)
    print('jmx samples %d (500 ms)' % len(jm))
    if pend: print('K_q TracingStage PendingTasks max %d (at +%.0f s), last %d' % (
        max(v for _, v in pend), (max(pend, key=lambda x: x[1])[0] - t0) if t0 else 0, pend[-1][1]))
    if compl and len(compl) > 1 and t0:
        c_in = [x for x in compl if x[0] >= t0]
        if len(c_in) > 1:
            print('TracingStage CompletedTasks during load %d -> %d (%.1f tasks/s)' % (c_in[0][1], c_in[-1][1],
                  (c_in[-1][1] - c_in[0][1]) / max(c_in[-1][0] - c_in[0][0], 1e-3)))
    if drop: print('dropped _TRACE max %d' % max(v for _, v in drop))
    if mut: print('MutationStage pending max %d' % max(v for _, v in mut))
    if rs: print('K RequestsSize max %d B (%.1f MiB)' % (max(v for _, v in rs), max(v for _, v in rs) / 2**20))
    if hu: print('heap used (JMX) max %.0f MiB' % (max(v for _, v in hu) / 2**20))
    # per 10 s: pending, completed rate
    if t0:
        line = []
        for k in range(0, 400, 10):
            a = [v for t, v in pend if t0 + k <= t < t0 + k + 10]
            if not a: continue
            line.append('+%d:%d' % (k, max(a)))
        print('PendingTasks max per 10 s:', ' '.join(line))
    for (j, n, ts) in steps:
        a, b = ts / 1000, ts / 1000 + 60
        pp = [(t, v) for t, v in pend if a <= t < b]
        req = [c for c in ok if a <= c[0] < b]
        slope = (pp[-1][1] - pp[0][1]) / max(pp[-1][0] - pp[0][0], 1e-3) if len(pp) > 1 else float('nan')
        cc = [(t, v) for t, v in compl if a <= t < b]
        crate = (cc[-1][1] - cc[0][1]) / max(cc[-1][0] - cc[0][0], 1e-3) if len(cc) > 1 else float('nan')
        print('ramp step %d N=%d: requests/s %.2f; PendingTasks first %s last %s max %s slope %.2f/s; consumer %.2f tasks/s' % (
            j, n, len(req) / 60, pp[0][1] if pp else '-', pp[-1][1] if pp else '-', max((v for _, v in pp), default='-'),
            slope, crate))
mt = [l.split(',') for l in rd('jmx-mt.csv').splitlines()[1:] if l and l[0].isdigit()]
if mt:
    s = col(mt, 1); e = col(mt, 2)
    print('memtable system_traces on-heap max: sessions %.0f MiB, events %.0f MiB' % (
        max((v for _, v in s), default=0) / 2**20, max((v for _, v in e), default=0) / 2**20))
# GC log
gcfiles = sorted(glob.glob(os.path.join(R, 'gc.log*')))
gcall = ''.join(open(f, errors='replace').read() for f in gcfiles)
pau = {}
for mm in re.finditer(r'^\[(\d{4}-\d\d-\d\dT[\d:.]+)([-+]\d{4})\]\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\((\d+)\) (Pause [^\n]*?) (\d+)M->(\d+)M\(\d+M\) (\d+\.\d+)ms', gcall, re.M):
    ts = dt.datetime.strptime(mm.group(1) + mm.group(2), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
    pau[(int(mm.group(4)), mm.group(5)[:11])] = (ts, mm.group(5), int(mm.group(6)), int(mm.group(7)), float(mm.group(8)))
hum = {}
for mm in re.finditer(r'GC\((\d+)\) Humongous regions: (\d+)->(\d+)', gcall):
    hum[int(mm.group(1))] = (int(mm.group(2)), int(mm.group(3)))
ev = sorted(pau.values())
if ev:
    after = [e[3] for e in ev]
    print('GCs %d; heap after GC max %d MiB median %d MiB; last 8 after-GC: %s' % (len(ev), max(after), stt.median(after), ' '.join(str(x) for x in after[-8:])))
    full = [e for e in ev if 'Full' in e[1]]
    print('Full GCs %d%s' % (len(full), ('; after MiB ' + ' '.join(str(e[3]) for e in full[-10:])) if full else ''))
    tend = ev[-1][0]
    stw = sum(min(e[4] / 1000, e[0] + e[4] / 1000 - (tend - 60)) for e in ev if e[0] + e[4] / 1000 >= tend - 60)
    print('STW share over last 60 s of GC log: %.0f%%' % (100 * stw / 60))
if hum:
    ids = sorted(hum)
    ha = [hum[i][1] for i in ids]
    if t0:
        # restrict to GCs after load start, by gc id order (pau has the timestamps)
        tmap = {k[0]: v[0] for k, v in pau.items()}
        ha_l = [hum[i][1] for i in ids if tmap.get(i, 0) >= t0]
    else:
        ha_l = ha
    print('U_h humongous regions after GC (16 MiB each): max %d (%.0f MiB), median during load %s, last 8: %s; before load max %s' % (
        max(ha), max(ha) * 16, stt.median(ha_l) if ha_l else '-', ' '.join(str(x) for x in ha[-8:]),
        max((hum[i][1] for i in ids if t0 and tmap.get(i, 0) < t0), default='-') if t0 else '-'))
print('to-space exhausted %d' % gcall.count('To-space exhausted'))
rss = [l.split() for l in rd('rss.txt').splitlines()]
rv = [int(r[1]) for r in rss if len(r) >= 3 and r[1].isdigit()]
if rv: print('RssAnon max %.0f MiB' % (max(rv) / 1024))
cg = [int(r[2]) for r in rss if len(r) >= 3 and r[2].isdigit()]
if cg: print('scope memory.current max %.0f MiB' % (max(cg) / 2**20))
th = [l.split() for l in rd('threads.txt').splitlines()]
th = [t for t in th if len(t) >= 7]
if th:
    print('threads samples %d: max NTR %d, runnable %d, lexer %d, TraceKeyspace %d, formatter %d; TracingStage top: %s' % (
        len(th), *[max(int(t[i]) for t in th) for i in range(1, 6)], ' '.join(t[6] for t in th)[:400]))
df = [l.split() for l in rd('df.txt').splitlines()]
if df: print('df last: %s' % ' '.join(df[-1]))
print('du at end:', rd('du-end.txt').replace('\n', ' ; '))
print('dumps:', ' '.join('%s (%d MiB)' % (os.path.basename(f), os.path.getsize(f) >> 20) for f in glob.glob(os.path.join(R, '*.hprof'))) or 'none')
