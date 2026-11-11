#!/usr/bin/env python3
"""Commit-log directory sampler. Usage: python3 -I sampler.py <commitlog_dir> <pidfile> <out_prefix> [period_s]
Every period (default 0.25 s) writes <out>.csv: t_ms,nfiles,maxfile,totalbytes,maps_n,maps_bytes  (file sizes by stat; maps_* = the
CommitLog-*.log mappings in /proc/<pid>/maps). On SIGTERM writes <out>.perfile.csv: name,first_ms,max_size,last_size."""
import os, sys, time, signal, re
d, pidf, out = sys.argv[1:4]
per = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
files = {}
stop = False
def h(*a):
    global stop; stop = True
signal.signal(signal.SIGTERM, h); signal.signal(signal.SIGINT, h)
def maps(pid):
    n = b = 0
    try:
        for ln in open(f'/proc/{pid}/maps'):
            if 'CommitLog-' in ln and '.log' in ln:
                a = ln.split()[0].split('-'); n += 1; b += int(a[1], 16) - int(a[0], 16)
    except Exception:
        pass
    return n, b
f = open(out + '.csv', 'w'); f.write('t_ms,nfiles,maxfile,totalbytes,maps_n,maps_bytes\n')
while not stop:
    t = int(time.time() * 1000)
    nf = mx = tot = 0
    try:
        for e in os.scandir(d):
            if e.name.endswith('.log'):
                try: sz = e.stat().st_size
                except FileNotFoundError: continue
                nf += 1; tot += sz; mx = max(mx, sz)
                r = files.setdefault(e.name, [t, 0, 0]); r[1] = max(r[1], sz); r[2] = sz
    except FileNotFoundError:
        pass
    try: pid = int(open(pidf).read().strip())
    except Exception: pid = 0
    mn, mb = maps(pid) if pid else (0, 0)
    f.write(f'{t},{nf},{mx},{tot},{mn},{mb}\n')
    time.sleep(per)
f.close()
with open(out + '.perfile.csv', 'w') as g:
    g.write('name,first_ms,max_size,last_size\n')
    for k, v in sorted(files.items()): g.write(f'{k},{v[0]},{v[1]},{v[2]}\n')
