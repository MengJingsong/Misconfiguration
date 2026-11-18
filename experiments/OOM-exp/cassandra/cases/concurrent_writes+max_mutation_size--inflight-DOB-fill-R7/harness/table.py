#!/usr/bin/env python3
# One markdown row per U1 run-2 arm (from the pc96 mirror): outcome, death time, U_peak, K, heap, MutationStage
# saturation, delivered (client ok MiB/s summed over clients), timeouts, forced GCs, dump holders if present.
#   table.py <mirror/arm> ...
import sys, os, re, glob, csv
MiB = 1048576.0
def m(p, s, d=''):
    x = re.search(p, s); return x.group(1) if x else d
def row(R):
    o = open(os.path.join(R, 'outcome.txt')).read(); name = os.path.basename(R)
    st = m(r'V=(\w+)', o); dj = int(m(r'directOOM=(\d+)', o, '0')); nn = int(m(r'nettyOOM=(\d+)', o, '0')); hh = int(m(r'heapOOM=(\d+)', o, '0'))
    fo = open(os.path.join(R, 'first-oom.txt'), errors='replace').read() if os.path.exists(os.path.join(R, 'first-oom.txt')) else ''
    if st == 'alive': out = 'survive'
    elif dj: out = '**direct OOM**' + (' (CommitLog.add)' if 'CommitLog.add' in fo[:6000] else ' (other stack)')
    elif nn: out = 'Netty-counter OOM'
    elif hh: out = 'heap OOM'
    else: out = 'DEAD?'
    death = '—'
    if st != 'alive':
        import datetime
        ls = int(m(r'(\d+) load start', open(os.path.join(R, 'args.txt')).read(), '0'))
        x = re.search(r'ERROR \[[^\]]+\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d+) .*', fo)
        if x and ls:
            t = datetime.datetime.strptime(x.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
            death = '%.0f' % ((t - ls) / 1000.0)
    sysgc = int(m(r'(\d+)', open(os.path.join(R, 'gcsys.txt')).read(), '-1')) if os.path.exists(os.path.join(R, 'gcsys.txt')) else -1
    ok = 0.0; to = 0; sent = 0
    for f in glob.glob(os.path.join(R, 'load-*.log')):
        t = open(f).read(); fl = m(r'(FINAL.*)', t, ''); ok += float(m(r'ok_MiBps=([\d.]+)', fl, '0')); to += int(m(r'WriteTimeoutException=(\d+)', fl, '0')); sent += int(m(r'FINAL sent=(\d+)', fl, '0'))
    blob = int(m(r'blob=(\d+)', o, '0'))
    dh = os.path.join(R, 'direct-holders.txt'); dob = net = rq = ''
    if os.path.exists(dh):
        t = open(dh).read(); dob = m(r'DataOutputBuffer scratch\s+([\d.]+) MiB', t); net = m(r'DIRECT_MEMORY_COUNTER=([\d.]+) MiB', t); rq = m(r'R: receive queue, queued LARGE frames\s+([\d.]+) MiB', t)
    return "| `%s` | %s | %.2f | %s×%s | %s | %s | %s | %s | %s | %s | %s | %s (≥24: %s) | %d | %d | %d / %d | %d | %s | %s |" % (
        name, m(r'direct=(\S+)', o), blob / MiB, m(r'ncoord=(\d+)', o), m(r'infl/client=(\d+)', o),
        ((m(r'vextra=\[([^\]]*)\]', o) + ' ' + m(r'vjvm=\[([^\]]*)\]', o)).strip() or '—'), out,
        death, m(r'U_peak=(\d+)', o), m(r'K_peak=(\d+)', o), m(r'heap_peak=(\d+)', o),
        m(r'mut_active_peak=(\d+)', o), m(r'active32=(\d+/\d+)', o), m(r'active>=24=(\d+)/', o), int(m(r'd_local_writes=(\d+)', o, '0')), int(m(r'd_dropped_mut=(\d+)', o, '0')), sent, to, sysgc, dob, rq)
print("| Arm | X (MiB) | value (MiB) | N×in-flight | change | outcome | death (s after load start) | U_peak (MiB) | K_peak (MiB) | heap peak | MutationStage active peak | load samples at 32 | writes applied on V | MUTATION_REQ dropped (expired) | client sent / timeouts | forced GCs | dump: DOB (MiB) | dump: R frames (MiB) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for R in sys.argv[1:]:
    if os.path.exists(os.path.join(R, 'outcome.txt')): print(row(R))
