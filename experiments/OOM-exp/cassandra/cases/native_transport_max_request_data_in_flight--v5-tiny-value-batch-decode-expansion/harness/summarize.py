#!/usr/bin/env python3
"""summarize.py <run dir>: one summary for an R13 run (from B14's): endpoint, responses by status, 'Batch too large' ERROR
lines, K_server / K_client, write-path-absent checks, held threads, heap after GC, GC STW share (each GC id once)."""
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
    if 'baseline done' in l or 'dump' in l: print('driver:', l)
# resolved in-flight limit (JMX StorageService)
C = None
for l in rd('resolved.txt').splitlines():
    mm = re.match(r'org.apache.cassandra.db:type=StorageService\|NativeTransportMaxConcurrentRequestsInBytes\|(\d+)', l)
    if mm: C = int(mm.group(1))
    if 'StorageService' in l: print('resolved:', l.split('|', 1)[1])
# client
rows = []; est_at = []; body = None
for f in sorted(glob.glob(os.path.join(R, 'client-p*.txt'))):
    for l in open(f):
        if l.startswith('# established'):
            mm = re.search(r'established=(\d+) body=(\d+)', l); body = int(mm.group(2))
            est_at.append(int(l.split(' at ')[1]))
        elif not l.startswith('#') and l.strip():
            rows.append(list(map(int, l.split())))
if est_at: print('client processes %d, body %s B, last established at %d' % (len(est_at), body, max(est_at)))
comp = []
for f in glob.glob(os.path.join(R, 'completions-p*.txt')):
    comp += [l.split() for l in open(f) if l.strip()]
comp.sort(key=lambda c: int(c[0]))
t0 = max(est_at) if est_at else 0
resp = [c for c in comp if c[3] == 'VOID' or c[3].startswith('ERR:')]
print('responses %d (VOID %d)' % (len(resp), sum(1 for c in resp if c[3] == 'VOID')))
st = {}
for c in comp:
    k = c[3][:60]; st[k] = st.get(k, 0) + 1
for k, v in sorted(st.items(), key=lambda x: -x[1])[:8]: print('  status x%d: %s' % (v, k))
if resp:
    lat = sorted(int(c[2]) for c in resp)
    print('response latency ms: min %d median %d max %d' % (lat[0], lat[len(lat) // 2], lat[-1]))
    print('first response +%.1f s, last response +%.1f s after last established' % ((int(resp[0][0]) - t0) / 1000, (int(resp[-1][0]) - t0) / 1000))
    span = (int(resp[-1][0]) - t0) / 1000
    if span > 0: print('response rate %.2f /s over first..last response' % (len(resp) / span))
by = {}
for r in rows:
    v = by.setdefault(r[0] // 1000, [0, 0]); v[0] += r[3]; v[1] += r[7] if len(r) > 7 else 0
if by:
    sf = max(v[1] for v in by.values())
    print('client outstanding max (sum over procs, per s) %d; sent_first max %d' % (max(v[0] for v in by.values()), sf))
    if C and body:
        charge = body - 1048576; adm = C // charge
        print('admitted by limit %d (C %d / charge %d); K_client = min(sent_first, admitted) x charge = %d' % (adm, C, charge, min(sf, adm) * charge))
# Batch too large ERROR lines
bt = 0
for f in glob.glob(os.path.join(R, 'system.log*')):
    bt += sum(1 for l in open(f, errors='replace') if 'batch_size_fail_threshold' in l and 'Batch for [r13.' in l)
print('Batch-too-large ERROR lines in system.log*: %d' % bt)
# jmx
jm = [l.split(',') for l in rd('jmx.csv').splitlines()[1:] if l and l[0].isdigit()]
jm = [r for r in jm if len(r) == 15]  # a row with an unregistered bean prints extra fields: skip it
def col(i):
    o = []
    for r in jm:
        try: o.append(float(r[i]))
        except (ValueError, IndexError): pass
    return o
if jm:
    rs = col(1); pc = col(2); mt = col(3); mb = col(4); mp = col(5); na = col(6); npd = col(7); du = col(8)
    wc = col(10); wto = col(11); mc = col(12); nps = col(13); npo = col(14)
    print('jmx samples %d (last at %+.1f s)' % (len(jm), (int(jm[-1][0]) - t0) / 1000))
    if rs:
        srt = sorted(rs[4:]) or sorted(rs)
        print('K_server RequestsSize max %d; last %d; median(after baseline) %d; series(MB) %s' % (max(rs), rs[-1], srt[len(srt) // 2], ' '.join('%.0f' % (x / 1e6) for x in rs)))
    if pc: print('PausedConnections max %d' % max(pc))
    if mt or mb: print('memtable heap max t %.1f MiB, big %.1f MiB' % (max(mt or [0]) / 2**20, max(mb or [0]) / 2**20))
    if mp: print('MutationStage pending max %d; completed first %d last %d' % (max(mp), (mc or [0])[0], (mc or [0])[-1]))
    if wc: print('ClientRequest Write count max %d; timeouts max %d' % (max(wc), max(wto or [0])))
    if na: print('NTR active max %d; NTR pending max %d' % (max(na), max(npd or [0])))
    if du: print('direct MemoryUsed max %.0f MiB; netpool size max %.0f MiB, overflow max %.0f MiB' % (max(du) / 2**20, max(nps or [0]) / 2**20, max(npo or [0]) / 2**20))
    print('last jmx row:', ','.join(jm[-1]))
th = [l.split() for l in rd('threads.txt').splitlines()]
th = [t for t in th if len(t) == 9]
if th:
    print('threads samples %d: max NTR %d, BatchMessage.execute %d, getMutations %d, wait %d, clog %d, memt %d, decode %d, verify %d' % (
        len(th), *[max(int(t[i]) for t in th) for i in range(1, 9)]))
    print('  decode series:', ' '.join(t[7] for t in th), '| execute series:', ' '.join(t[2] for t in th), '| last sample:', ' '.join(th[-1][1:]))
rss = [int(x) for x in re.findall(r'rssanon_kb=(\d+)', rd('heapinfo.txt'))]
if rss: print('RssAnon max %.0f MiB' % (max(rss) / 1024))
# GC: each (GC id, pause line) once across rotated files
seen = {}
for f in sorted(glob.glob(os.path.join(R, 'gc.log*'))):
    for l in open(f, errors='replace'):
        mm = re.search(r'\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\((\d+)\) (Pause [^\n]*?) (\d+)M->(\d+)M\(\d+M\) (\d+\.\d+)ms', l)
        if mm: seen[(int(mm.group(2)), mm.group(3))] = (float(mm.group(1)), mm.group(3), int(mm.group(4)), int(mm.group(5)), float(mm.group(6)))
ev = sorted(seen.values())
if ev:
    print('GCs %d; heap after GC max %d MiB; last 5 after-GC: %s' % (len(ev), max(e[3] for e in ev), ' '.join(str(e[3]) for e in ev[-5:])))
    print('  first-10 after-GC (baseline): %s' % ' '.join(str(e[3]) for e in ev[:10]))
    full = [e for e in ev if 'Full' in e[1]]
    print('  Full GCs %d: after-GC MiB %s' % (len(full), ' '.join(str(e[3]) for e in full[:40])))
    tend = ev[-1][0]
    last = sum(e[4] for e in ev if e[0] >= tend - 60) / 1000
    print('pauses %d; STW share over last 60 s of GC log: %.0f%%; Pause Full %d' % (len(ev), 100 * last / 60, len(full)))
cpu = rd('clientcpu.txt').splitlines()
if cpu: print('client cpu last sample:', cpu[-2][:200] if len(cpu) > 1 else cpu[-1][:200])
print('dumps:', ' '.join('%s (%d MiB)' % (os.path.basename(f), os.path.getsize(f) >> 20) for f in glob.glob(os.path.join(R, '*.hprof'))) or 'none')
