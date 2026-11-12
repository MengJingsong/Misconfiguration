#!/usr/bin/env python3
"""Self-check (results §5) of file_cache_size-chunk_cache_eviction-weighted_size--autonomous: re-parses the raw files
with its own code (no import of the analyzer). usage: python3 -I selfcheck.py <logs dir, e.g. /mydata/jingsong-cass-s4/o06/logs/run1>"""
import os, re, sys, glob
D = sys.argv[1]; U = os.path.join(D, 'unit'); C = os.path.join(D, 'cluster'); MiB = 1 << 20
print('== unit')
for x in sorted(glob.glob(os.path.join(U, 'junit-*.xml'))):
    s = open(x).read(); m = re.search(r'tests="(\d+)".*?failures="(\d+)"|failures="(\d+)".*?tests="(\d+)"', s, re.S)
    print(os.path.basename(x), 'errors="0"' in s and 'failures="0"' in s and 'ok' or 'NOT OK')
probe = {}
for l in open(os.path.join(U, 'probe-lines.txt')):
    if l.startswith('PROBE '):
        kv = dict(re.findall(r'(\w+)=(\S+)', l)); probe[int(kv['F'])] = kv
for F, kv in sorted(probe.items()):
    if 'instance' in kv: print('F=%d instance=%s cacheSize=%s' % (F, kv['instance'], kv['cacheSize'])); continue
    cap = (F - 32) * MiB; mw = int(kv['maxW'])
    print('F=%d cap=%s (expected %d: %s) maxW=%d (<= cap: %s, >= cap-65536: %s) maxE=%s poolSize=%s (<= F MiB: %s) overflow=%s evictions=%s' % (
        F, kv['cap'], cap, int(kv['cap']) == cap, mw, mw <= cap, mw >= cap - 65536, kv['maxE'], kv['poolSize'],
        int(kv['poolSize']) <= F * MiB, kv['overflow'], kv['evictions']))
if 64 in probe and 160 in probe:
    print('ratio maxW(160)/maxW(64) = %.4f' % (int(probe[160]['maxW']) / int(probe[64]['maxW'])))
print('== cluster')
marks = [l.split(' ', 1) for l in open(os.path.join(C, 'marks.txt'))]
win = {}
for t, r in marks:
    m = re.match(r'F=(\d+) (\w+)', r.strip())
    if m: win.setdefault(int(m.group(1)), {})[m.group(2)] = int(t)
base = None
for F in sorted(win):
    w = win[F]
    hdr = None; vals = []
    for l in open(os.path.join(C, 'jmx-%d.csv' % F)):
        p = l.rstrip('\n').split(',')
        if p[0] == 'epoch_ms': hdr = p; continue
        vals.append(dict(zip(hdr, p)))
    inr = [v for v in vals if w['read_start'] - 10000 <= int(v['epoch_ms']) <= w['tail']]
    lst = [v for v in vals if max(w['read_start'], w['read_end'] - 60000) <= int(v['epoch_ms']) <= w['read_end']]
    tl = [int(v['direct_used']) for v in vals if w['read_end'] + 5000 <= int(v['epoch_ms']) <= w['tail']]
    sizes = [int(v['cc_size']) for v in inr if v['cc_size']]
    caps = {v['cc_capacity'] for v in inr}
    d = sum(int(v['direct_used']) for v in lst) / len(lst)
    tm = sum(tl) / len(tl)
    if F == 32: base = d; tbase = tm
    print('     tail direct mean %.2f MiB, tail delta %.2f MiB' % (tm / MiB, (tm - tbase) / MiB))
    print('F=%d capacities %s size max %s, last-60s sizes %s..%s; pool max %d; overflow max %d; direct last-60s mean %.2f MiB delta %.2f MiB' % (
        F, caps, max(sizes) if sizes else None, min(int(v['cc_size']) for v in lst if v['cc_size']) if sizes else None,
        max(int(v['cc_size']) for v in lst if v['cc_size']) if sizes else None,
        max(int(v['ccpool_size']) for v in inr), max(int(v['ccpool_overflow']) for v in inr), d / MiB, (d - base) / MiB))
    cq = [l for l in open(os.path.join(C, 'cql-%d.txt' % F)) if w['read_start'] - 10000 <= int(l.split()[0]) <= w['tail']]
    cs = [int(m.group(1)) for l in cq for m in [re.search(r'chunks \|\s*\d+ \|\s*(\d+)', l)] if m]
    print('     cql samples %d, size_bytes max %s' % (len(cq), max(cs) if cs else None))
    sr = open(os.path.join(C, 'stress-read-%d.log' % F)).read()
    print('     stress: %s; %s' % (re.search(r'Total partitions\s*:\s*([\d,]+)', sr).group(1), re.search(r'Total errors\s*:\s*([\d,]+)', sr).group(1)))
sl = open(sorted(glob.glob(os.path.join(C, 'system-after-*.log')), key=os.path.getmtime)[-1]).read()
print('system.log: ERROR lines %d, OutOfMemoryError %d, "Maximum memory usage reached" %d' % (
    len(re.findall(r'^ERROR', sl, re.M)), sl.count('java.lang.OutOfMemoryError'), sl.count('Maximum memory usage reached')))
