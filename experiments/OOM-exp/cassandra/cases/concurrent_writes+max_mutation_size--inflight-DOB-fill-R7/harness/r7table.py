#!/usr/bin/env python3
# R7 per-arm table from the driver mirror. Windows: L = from "load start" (client launch, design's literal window);
# S = from the first client's "start epoch_ms" (clients send from then; amendment A3). Both end at V's death (last
# good sample) or load end. Applied = local writes x blob over the S window up to death / load end.
import csv, os, re, glob, sys
M = '/mydata/s4/r7-w1/mirror'; MiB = 1048576.0
names = sys.argv[1:] or sorted((d for d in os.listdir(M) if os.path.isfile(os.path.join(M, d, 'outcome.txt'))), key=lambda d: os.path.getmtime(os.path.join(M, d, 'outcome.txt')))
print("| Arm | Direct (resolved) | V | First OOM | t_death from S (s) | U_peak | K_peak | heap_peak | active=32 L / S | applied MiB/s (S) | forced GCs | coord heapOOM, ms0640 si/so, MemAvail min | clients ok/err |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for n in names:
    d = os.path.join(M, n); o = open(os.path.join(d, 'outcome.txt')).read(); a = open(os.path.join(d, 'args.txt')).read()
    ls = int(re.search(r'(\d+) load start', a)[1]); le = int(re.search(r'(\d+) load end', a)[1])
    dead = re.search(r'(\d+) V dead', a); dead = int(dead[1]) if dead else None
    blob = int(re.search(r'blob=(\d+)', a)[1])
    starts = []
    for f in glob.glob(os.path.join(d, 'load-*.log')):
        m = re.search(r'start epoch_ms=(\d+)', open(f).read())
        if m: starts.append(int(m[1]))
    ss = min(starts) if starts else ls
    rows = [r for r in csv.DictReader(open(os.path.join(d, 'samples.csv'))) if r['direct_used'] not in ('NA', '-1', '')]
    def win(t0):
        return [r for r in rows if t0 <= int(r['epoch_ms']) <= (dead or le)]
    def a32(w): return "%d/%d" % (sum(1 for r in w if int(r['mut_active']) >= 32), len(w))
    wS = win(ss); wL = win(ls)
    lw = [int(r['local_writes']) for r in wS if int(r['local_writes']) >= 0]
    dur = (int(wS[-1]['epoch_ms']) - int(wS[0]['epoch_ms'])) / 1000.0 if len(wS) > 1 else 1
    appl = (lw[-1] - lw[0]) * blob / MiB / dur if len(lw) > 1 else 0
    fg = os.path.join(d, 'forced-gc.txt'); gcs = int(open(fg).readline().strip() or -1) if os.path.exists(fg) else -1
    m = re.search(r'resolved_direct=(\d+)MiB \| V=(\w+) directOOM=(\d+) heapOOM=(\d+) nettyOOM=(\d+) oom_kill=(\S+)', o)
    pk = lambda k: re.search(k + r'=(\d+)', o)[1]
    fo = open(os.path.join(d, 'first-oom.txt')).read() if os.path.exists(os.path.join(d, 'first-oom.txt')) else ''
    th = re.search(r'ERROR \[([^\]]+)\]', fo); kind = 'direct' if 'Direct buffer memory' in fo[:3000] else ('heap' if 'Java heap' in fo[:3000] else ('netty' if 'OutOfDirectMemoryError' in fo[:3000] else '-'))
    first = '-' if not th else "%s %s%s" % (kind, th[1], ' CommitLog.add' if 'CommitLog.add' in fo else '')
    v = re.search(r'valid: coord_heapOOM=(\d+) ms0640_load_si=(\d+) so=(\d+).*?memavail_min_MiB=(\S+).*clients ok=(\d+) err=(\d+)', o)
    vv = "%s, %s/%s, %s" % (v[1], v[2], v[3], v[4]) if v else '?'
    td = "%.0f" % ((dead - ss) / 1000.0) if dead else '-'
    print("| %s | %s | %s | %s | %s | %s | %s | %s | %s / %s | %.0f | %d | %s | %s |" % (n, m[1], m[2] + (' (dOOM %s, hOOM %s, netty %s, oom_kill %s)' % (m[3], m[4], m[5], m[6])), first, td,
        pk('U_peak'), pk('K_peak'), pk('heap_peak'), a32(wL), a32(wS), appl, gcs, vv, ("%s/%s" % (v[5], v[6])) if v else '?'))
