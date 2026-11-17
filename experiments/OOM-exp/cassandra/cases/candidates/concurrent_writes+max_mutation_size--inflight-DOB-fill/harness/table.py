#!/usr/bin/env python3
# One row per arm (markdown): outcome, time to death, U_peak, heap peak, MutationStage active peak, delivered, timeouts, forced GCs.
import sys, os, re, glob, csv
MiB = 1048576.0
def row(R):
    a = open(os.path.join(R, 'args.txt')).read(); o = open(os.path.join(R, 'outcome.txt')).read()
    name = os.path.basename(R)
    m = lambda p, s, d='': (re.search(p, s).group(1) if re.search(p, s) else d)
    st = m(r'V=(\w+)', o); dj = int(m(r'directOOM=(\d+)', o, '0')); nn = int(m(r'nettyOOM=(\d+)', o, '0')); hh = int(m(r'heapOOM=(\d+)', o, '0'))
    out = 'survive' if st == 'alive' else ('**U1 direct OOM**' if dj and not nn else ('Netty-counter OOM' if nn and not dj else ('heap OOM' if hh else 'DEAD?')))
    if st != 'alive' and dj and nn: out = 'both (first: %s)' % ('JDK' if open(os.path.join(R,'first-oom.txt')).read().find('Direct buffer memory') < open(os.path.join(R,'first-oom.txt')).read().find('OutOfDirect') else 'Netty')
    ls = int(m(r'(\d+) load start', a, '0'))
    rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
    dead = next((int(r['epoch_ms']) for r in rows if r['direct_used'] == 'NA' and int(r['epoch_ms']) > ls), None)
    t = '%d s' % ((dead - ls) / 1000) if dead and st != 'alive' else '—'
    def pk(k):
        v = [float(r[k]) for r in rows if r[k] not in ('NA', '') and float(r[k]) >= 0]; return max(v) if v else -1
    sysgc = sum(open(f, errors='replace').read().count('System.gc()') for f in glob.glob(os.path.join(R, 'V-logs/gc.log*')))
    cl = m(r'ok_MiBps=([\d.]+)', o, '?'); to = m(r'd_write_timeouts=(\d+)', o, '?')
    X = m(r'direct=(\S+?)\(', o); args = m(r'blob=(\d+) writers=(\d+) infl=(\d+) rate=([\d.]+)', o)
    bl = int(m(r'blob=(\d+)', o)); w = m(r'writers=(\d+)', o); i = m(r'infl=(\d+)', o); rt = m(r'rate=([\d.]+)', o)
    vx = m(r'vextra=\[([^\]]*)\]', o); vj = m(r'vjvm=\[([^\]]*)\]', o)
    net = m(r'DIRECT_MEMORY_COUNTER=([\d.]+) MiB', open(os.path.join(R, 'direct-holders.txt')).read()) if os.path.exists(os.path.join(R, 'direct-holders.txt')) else ''
    dob = m(r'DataOutputBuffer scratch\s+([\d.]+) MiB', open(os.path.join(R, 'direct-holders.txt')).read()) if os.path.exists(os.path.join(R, 'direct-holders.txt')) else ''
    return "| `%s` | %s | %.2f MiB | %s×%s @%s/s | %s | %s | %s | %.0f | %.0f | %d | %s | %s | %d | %s | %s |" % (
        name, X, bl / MiB, w, i, rt, (vx + ' ' + vj).strip() or '—', out, t, pk('direct_used') / MiB, pk('heap_used') / MiB, pk('mut_active'), cl, to, sysgc, dob, net)
print("| Arm | X (MiB) | mutation | writers×in-flight @offered | change | outcome | death after load start | U_peak (MiB) | heap peak | MutationStage active peak | delivered MiB/s | write timeouts | forced GCs (`System.gc()` lines) | dump: DOB (MiB) | dump: Netty counter (MiB) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for R in sys.argv[1:]:
    if os.path.exists(os.path.join(R, 'outcome.txt')): print(row(R))
