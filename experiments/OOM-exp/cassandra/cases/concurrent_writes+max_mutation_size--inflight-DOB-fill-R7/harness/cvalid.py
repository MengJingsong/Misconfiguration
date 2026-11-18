#!/usr/bin/env python3
# R7 arm validity (design §2.7, pre-declared): from the driver mirror of one arm.
# Checks: coordinator heap OOMs, ms0640 swap in/out (vmstat si/so) and MemAvailable >= 4 GiB during the load window,
# client totals; prints one "valid:" line (the K_peak / active32 / MaxDirect / oom_kill checks read outcome.txt).
import sys, os, re, glob
M = sys.argv[1]
a = open(os.path.join(M, 'args.txt')).read() if os.path.exists(os.path.join(M, 'args.txt')) else ''
ls = int((re.search(r'(\d+) load start', a) or [0, 0])[1]) // 1000
le = int((re.search(r'(\d+) load end', a) or [0, 0])[1]) // 1000 or 10**12
heapoom = sum(int(open(f).read().strip() or 0) for f in glob.glob(os.path.join(M, 'C*-heapoom.txt')))
si = so = 0; idmin = 100; n = 0
for line in open(os.path.join(M, 'vmstat.txt')) if os.path.exists(os.path.join(M, 'vmstat.txt')) else []:
    p = line.split()
    if len(p) < 18 or not p[1].isdigit(): continue
    # "<epoch> r b swpd free buff cache si so bi bo in cs us sy id wa st"; load window only
    if not (ls <= int(p[0]) <= le): continue
    si += int(p[7]); so += int(p[8]); idmin = min(idmin, int(p[15])); n += 1
memmin = 10**9; swapused = 0
for line in open(os.path.join(M, 'free.txt')) if os.path.exists(os.path.join(M, 'free.txt')) else []:
    p = line.split()
    if len(p) >= 3 and ls <= int(p[0]) <= le: memmin = min(memmin, int(p[1])); swapused = max(swapused, int(p[2]))
ok = err = 0; errs = []
for f in glob.glob(os.path.join(M, 'load-*.log')):
    t = open(f).read(); m = re.search(r'FINAL sent=(\d+) ok=(\d+) err=(\d+).*errs=(.*)', t)
    if m: ok += int(m[2]); err += int(m[3]); errs.append(m[4].strip())
    else:
        ms = re.findall(r'ok=(\d+) .*?err=(\d+)', t)
        if ms: ok += int(ms[-1][0]); err += int(ms[-1][1])
print("valid: coord_heapOOM=%d ms0640_load_si=%d so=%d(KiB/s summed) vmstat_id_min=%d (n=%d) memavail_min_MiB=%s swap_used_max_MiB=%d | clients ok=%d err=%d %s" % (
    heapoom, si, so, idmin, n, memmin if memmin < 10**9 else 'NA', swapused, ok, err, ';'.join(e for e in errs if e != '{}')[:300]))
