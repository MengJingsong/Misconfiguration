#!/usr/bin/env python3
"""Readings of the max_offset cluster tier. usage: analyze.py <cluster dir>  (contains one directory per arm)
Prints a table and EXPECTED lines for B3f / amendment C5 (frozen before the run)."""
import glob, os, re, sys, datetime
d = sys.argv[1]
ARMS = ['s1', 's4', 's16', 'n1', 'b1', 'h1', 'p1']
def rd(p):
    return open(p, errors='replace').read() if os.path.exists(p) else ''
def sizes(arm):
    t = rd('%s/%s/sizes.txt' % (d, arm)); r = {}
    for k, pat in (('data', 'Data.db'), ('index', 'Index.db'), ('si', 'SI_')):
        m = re.search(r"\*[-]?%s\S*\s+(\d+)" % re.escape(pat), t) or re.search(r"\*%s\S*\s+(\d+)" % re.escape(pat), t)
        r[k] = int(m.group(1)) if m else None
    m = re.search(r'data_dir_bytes (\d+)', t); r['dir'] = int(m.group(1)) if m else None
    return r
def gcmax(arm, lo=None, hi=None):
    best = 0
    for l in rd('%s/%s/gc.log' % (d, arm)).splitlines():
        if 'Pause' not in l: continue
        m = re.search(r'(\d+)M->(\d+)M\(', l); t = re.match(r'\[(\d{4}-[^\]]+)\]', l)
        if not m or not t: continue
        if lo is not None:
            ts = datetime.datetime.strptime(t.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
            if ts < lo or ts > hi: continue
        best = max(best, int(m.group(2)))
    return best
def heapmax(arm):
    best = 0
    for l in rd('%s/%s/heap.csv' % (d, arm)).splitlines()[1:]:
        p = l.split(',')
        if len(p) > 1 and p[1].strip().isdigit(): best = max(best, int(p[1]))
    return best
def disk(arm):
    cl = []; dt = []
    for l in rd('%s/%s/disk.csv' % (d, arm)).splitlines()[1:]:
        p = l.split(',')
        if len(p) == 4: dt.append(int(p[1])); cl.append(int(p[2]))
    return cl, dt
R = {}
print('%-5s %10s %12s %12s %12s %12s %9s %9s %10s %6s' % ('arm', 'rows', 'Data.db', 'Index.db', 'SI', 'dataDir', 'maxCLmiB', 'maxHeapMiB', 'maxPostGC', 'errs'))
for a in ARMS:
    if not os.path.isdir('%s/%s' % (d, a)): continue
    s = sizes(a); cl, dt = disk(a); cmd = rd('%s/%s/cmdlog.txt' % (d, a))
    rows = re.search(r'rows=(\d+)', cmd); errs = len([l for l in rd('%s/%s/log-errors.txt' % (d, a)).splitlines() if l.strip()])
    sysl = rd('%s/%s/system.log' % (d, a))
    R[a] = dict(s, rows=int(rows.group(1)) if rows else 0, maxcl=max(cl) if cl else 0, maxheap=heapmax(a), post=gcmax(a), errs=errs,
                assertion=len(re.findall(r'cannot be greater than|AssertionError', sysl)), cl=cl, dt=dt,
                guard='GUARD FAILED' in cmd, ran='== %s end' % a in cmd)
    r = R[a]
    print('%-5s %10d %12s %12s %12s %12s %9.1f %9.0f %10d %6d' % (a, r['rows'], r['data'], r['index'], r['si'], r['dir'], r['maxcl'] / 1048576, r['maxheap'] / 1048576, r['post'], errs))
ok = fail = 0
def expect(name, cond, detail):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print('EXPECTED %s: %s  %s' % (name, detail, 'PASS' if cond else 'FAIL'))
for a, r in R.items():
    if r['guard']: print('NOTE %s not run: disk guard failed' % a); continue
    expect('%s ran to the end and has one Data.db' % a, r['ran'] and r['data'] not in (None, 0), 'Data.db %s' % r['data'])
    expect('%s no AssertionError / "cannot be greater than" in system.log' % a, r['assertion'] == 0, 'count %d' % r['assertion'])
    expect('%s sampled heap stays within the -Xmx cap' % a, r['maxheap'] <= (4096 if a == 'h1' else 2048) * 1048576 * 1.01, 'max used %.0f MiB' % (r['maxheap'] / 1048576))
def ratio(a, b, key):
    if a in R and b in R and R[a].get(key) and R[b].get(key): return R[a][key] / R[b][key]
for key in ('data', 'index', 'si'):
    x = ratio('s4', 's1', key)
    if x: expect('s4/s1 %s bytes ratio 3..5 (rows x4)' % key, 3 <= x <= 5, '%.2f' % x)
    y = ratio('s16', 's4', key)
    if y: expect('s16/s4 %s bytes ratio 3..5 (rows x4)' % key, 3 <= y <= 5, '%.2f' % y)
if 's16' in R and 's1' in R and R['s16']['post'] and R['s1']['post']:
    x = R['s16']['post'] / R['s1']['post']
    expect('C5: max post-collection heap s16 within 1.5 x s1', x <= 1.5, '%d / %d = %.2f' % (R['s16']['post'], R['s1']['post'], x))
elif 's4' in R and 's1' in R:
    x = R['s4']['post'] / R['s1']['post']
    print('INFO (s16 not run) max post-collection heap s4 / s1 = %.2f (C5 asks for s16 within 1.5)' % x)
if 'n1' in R and 's1' in R:
    expect('n1 has no SI file', R['n1']['si'] in (0, None), 'SI bytes %s' % R['n1']['si'])
    x = R['n1']['data'] / R['s1']['data']
    expect('n1 Data.db within 5 percent of s1 (the index adds files, not data)', abs(x - 1) <= 0.05, '%.3f' % x)
if 'p1' in R and 's1' in R:
    p = R['p1']; mb = 1048576
    expect('p1 commit log stays within 64 MiB + 2 segments (<= 128 MiB)', p['maxcl'] <= 128 * mb, 'max %.1f MiB' % (p['maxcl'] / mb))
    # instrument fix after the first p1 reading: the data dir shrinks during the final compaction, so compare inside the load window (cmdlog load start/end)
    cmd = rd('%s/p1/cmdlog.txt' % d); ls = int(re.search(r'load start (\d+)', cmd).group(1)); le = int(re.search(r'load end (\d+)', cmd).group(1))
    rows_ = [l.split(',') for l in rd('%s/p1/disk.csv' % d).splitlines()[1:] if l.count(',') == 3]
    mid = [int(r[1]) for r in rows_ if ls + (le - ls) * 0.4 <= int(r[0]) <= ls + (le - ls) * 0.6]; end = [int(r[1]) for r in rows_ if int(r[0]) >= le - 4000 and int(r[0]) <= le + 2000]
    expect('p1 data keeps growing in the load window (60 percent of the load vs the end)', bool(mid) and bool(end) and max(end) > max(mid), 'data %d -> %d' % (max(mid), max(end)))
    clw = [int(r[2]) for r in rows_ if ls <= int(r[0]) <= le]
    expect('p1 commit log stays near its 64 MiB cap during the load (<= 2 x 64 MiB + 32 MiB)', max(clw) <= 160 * 1048576, 'max in the load window %.0f MiB, median %.0f MiB' % (max(clw) / 1048576, sorted(clw)[len(clw) // 2] / 1048576))
    expect('s1 commit log (cap 1024 MiB) reaches more than p1', R['s1']['maxcl'] > p['maxcl'], 's1 %.1f MiB vs p1 %.1f MiB' % (R['s1']['maxcl'] / mb, p['maxcl'] / mb))
if 'h1' in R and 's1' in R:
    print('INFO heap control: max sampled used h1 (-Xmx4G) %.0f MiB vs s1 (-Xmx2G) %.0f MiB; max post-GC h1 %d vs s1 %d MiB' % (R['h1']['maxheap'] / 1048576, R['s1']['maxheap'] / 1048576, R['h1']['post'], R['s1']['post']))
if 'b1' in R:
    print('INFO bti arm: Data.db %s SI %s; ls: %s' % (R['b1']['data'], R['b1']['si'], ' '.join(sorted(set(re.findall(r'\b(\w\w-\d+-\w+)-Data', rd('%s/b1/ls-sstable-dir.txt' % d)))))))
print('SUMMARY expectations pass=%d fail=%d' % (ok, fail))
