#!/usr/bin/env python3
"""Compare cluster readings with the frozen B3f/B3g. Usage: cluster-analyze.py <run1/cluster dir>"""
import re, sys, os
d = sys.argv[1]; MiB = 1 << 20
A = {'default': 8192, 'p1m': 1048576, 'p16m': 8388608, 'control': 8388608}
Pv = {'default': 8192, 'p1m': 1048576, 'p16m': 16777216, 'control': 16777216}
res = {}
for lab in ['default', 'p1m', 'p16m', 'control']:
    o = os.path.join(d, lab)
    if not os.path.isdir(o): continue
    def hb(f):
        # defect D2: on JDK 11 the line is '[B (java.base@11...)', so read it from the full histogram
        m = re.search(r'^\s*\d+:\s+(\d+)\s+(\d+)\s+\[B \(java\.base', open(os.path.join(o, f)).read(), re.M); return int(m.group(2))
    h0, h1 = hb('hist0-full.txt'), hb('hist1-full.txt')
    def rc(f):
        t = open(os.path.join(o, f)).read()
        m = re.search(r'Row Cache\s*:\s*entries (\d+), size ([^,]+), capacity ([^,]+), (\d+) hits, (\d+) requests', t)
        return tuple(m.groups()) if m else None
    rb, ra = rc('info-before.txt'), rc('info-after.txt')
    misses = (int(ra[4]) - int(ra[3])) - (int(rb[4]) - int(rb[3]))
    j = open(os.path.join(o, 'jfr.txt')).read()
    n_tb = int(re.search(r'tempbuf_events=(\d+)', j).group(1)); mx = int(re.search(r'tempbuf_max_len=(\d+)', j).group(1))
    sizes = re.findall(r'arrayLength=(\d+) count=(\d+) distinct_threads=(\d+)', j)
    ss = [l for l in open(os.path.join(o, 'tablestats-after.txt')) if 'SSTable count' in l]
    rd = open(os.path.join(o, 'read.log')).read().strip().splitlines()
    res[lab] = dict(h0=h0, h1=h1, dH=h1 - h0, misses=misses, rc_after=ra, tb=n_tb, tbmax=mx, sizes=sizes, sst=ss[0].strip() if ss else '?', read=rd[-1] if rd else '')
    r = res[lab]
    print(f"[{lab}] P={Pv[lab]} A(P)={A[lab]} H0={h0} H1={h1} dH={r['dH']} ({r['dH']/MiB:.2f} MiB) read-pass misses={misses} rowcache_after={ra} "
          f"{r['sst']} read='{r['read']}' tempbuf_events={n_tb} tempbuf_sizes={sizes} tempbuf_max={mx} (>P? {mx > Pv[lab]})")
print("--- B3g row checks")
offh = [l for l in ['default', 'p1m', 'p16m'] if l in res]
none_tb = all(res[l]['tb'] == 0 for l in offh)
large_tb = any(int(s) >= 1 << 20 for l in offh for s, _, _ in res[l]['sizes'])
miss64 = all(res[l]['misses'] == 64 for l in offh)
sst0 = all(res[l]['sst'].endswith(': 0') for l in offh)
over = any(res[l]['tbmax'] > Pv[l] for l in res)
print(f"any temp-buffer allocation > P: {over}")
print(f"64 row-cache misses on every read pass: {miss64}; SSTable count 0 everywhere: {sst0}")
print(f"temp-buffer allocations at any P (offheap runs): {not none_tb}; any of size >= 1 MiB: {large_tb}")
for l in offh:
    print(f"|dH| < 16 MiB at {l}: {abs(res[l]['dH']) < 16*MiB}")
if 'p1m' in res and 'p16m' in res and res['p1m']['dH']:
    print(f"dH(16M)/dH(1M) = {res['p16m']['dH']/res['p1m']['dH']:.2f}")
