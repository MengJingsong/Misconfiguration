#!/usr/bin/env python3
"""Readings of the super_block_size cluster tier. usage: analyze.py <cluster dir> (one directory per arm).
Prints a table and EXPECTED lines for B3f and amendment C3. Rule written before any cluster reading: "does not move with the
constant" means (max - min of the post-collection heap peak over constants 16/64/256 at option 64) < 0.25 x (max - min over options
8/64/512 at constant 64), and SI bytes within 5 percent over the constants."""
import os, re, sys, datetime
d = sys.argv[1]
def rd(p): return open(p, errors='replace').read() if os.path.exists(p) else ''
ARMS = ['o8c64', 'o64c64', 'o512c64', 'o64c16', 'o64c256', 'pfx64']
def window(a):
    t = rd('%s/%s/windows.txt' % (d, a)); s = re.search(r'COMPACT_START (\d+)', t); e = re.search(r'COMPACT_END (\d+)', t)
    return (int(s.group(1)), int(e.group(1))) if s and e else None
def gcmax(a, lo, hi):
    best = 0
    for l in rd('%s/%s/gc.log' % (d, a)).splitlines():
        if 'Pause' not in l: continue
        m = re.search(r'(\d+)M->(\d+)M\(', l); t = re.match(r'\[(\d{4}-[^\]]+)\]', l)
        if not m or not t: continue
        ts = datetime.datetime.strptime(t.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
        if lo <= ts <= hi: best = max(best, int(m.group(2)))
    return best
def heapmax(a, lo, hi):
    best = 0
    for l in rd('%s/%s/heap.csv' % (d, a)).splitlines()[1:]:
        p = l.split(',')
        if len(p) > 1 and p[0].strip().isdigit() and p[1].strip().isdigit() and lo <= int(p[0]) <= hi: best = max(best, int(p[1]))
    return best
def segments(a, w):
    n = 0
    for l in rd('%s/%s/system.log' % (d, a)).splitlines():
        if 'Flushed index segment' not in l: continue
        m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d+)', l)
        if m:
            ts = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
            if w[0] <= ts <= w[1] + 2000: n += 1
    return n
def sz(a, pat):
    m = re.search(r'\*%s\S*\s+(\d+)' % re.escape(pat), rd('%s/%s/sizes.txt' % (d, a)))
    return int(m.group(1)) if m else None
R = {}
print('%-8s %6s %10s %10s %10s %9s %9s %7s %s' % ('arm', 'rows', 'Data.db', 'SI', 'compactS', 'postGCMiB', 'sampMiB', 'segs', 'OnDiskIndexBuilder loaded from'))
for a in ARMS:
    if not os.path.isdir('%s/%s' % (d, a)): continue
    w = window(a); cmd = rd('%s/%s/cmdlog.txt' % (d, a))
    if not w: print(a, 'no compaction window'); continue
    cl = rd('%s/%s/classload-ondiskindex.txt' % (d, a)); m = re.search(r'OnDiskIndexBuilder\s+source: (\S+)', cl)
    sysl = rd('%s/%s/system.log' % (d, a))
    rows = re.search(r'rows=(\d+)', cmd)
    R[a] = dict(rows=int(rows.group(1)) if rows else 0, data=sz(a, '-Data.db') or sz(a, 'Data.db'), si=sz(a, 'SI_'), post=gcmax(a, *w) // 1, samp=heapmax(a, *w) / 1048576, seg=segments(a, w),
                secs=(w[1] - w[0]) / 1000, src=m.group(1) if m else '?', bad=len(re.findall(r'AssertionError|java\.lang\.OutOfMemoryError', sysl)), one='one sstable' in cmd and 'NOT one sstable' not in cmd,
                ran='== %s end' % a in cmd)
    r = R[a]
    print('%-8s %6d %10s %10s %10.0f %9d %9.0f %7d %s' % (a, r['rows'], r['data'], r['si'], r['secs'], r['post'], r['samp'], r['seg'], r['src']))
ok = fail = 0
def expect(name, cond, detail):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print('EXPECTED %s: %s  %s' % (name, detail, 'PASS' if cond else 'FAIL'))
for a, r in R.items():
    expect('%s ran, compacted to one sstable, no AssertionError/OutOfMemoryError in system.log' % a, r['ran'] and r['one'] and r['bad'] == 0, 'one=%s bad=%d' % (r['one'], r['bad']))
for a, c in (('o64c16', '/conf/'), ('o64c256', '/conf/'), ('o64c64', '/build/')):
    if a in R: expect('%s: OnDiskIndexBuilder loaded from %s' % (a, c), c in R[a]['src'] and (c != '/build/' or 'conf' not in R[a]['src']), R[a]['src'])
if all(a in R for a in ('o8c64', 'o64c64', 'o512c64')):
    o = [R[a] for a in ('o8c64', 'o64c64', 'o512c64')]
    expect('B3f: segments fall as the option rises (8 > 64 > 512)', o[0]['seg'] > o[1]['seg'] > o[2]['seg'], '%d %d %d' % (o[0]['seg'], o[1]['seg'], o[2]['seg']))
    expect('B3f: peak post-collection heap rises with the option (8 < 64 < 512)', o[0]['post'] < o[1]['post'] < o[2]['post'], '%d %d %d MiB' % (o[0]['post'], o[1]['post'], o[2]['post']))
    if all(a in R for a in ('o64c16', 'o64c256')):
        c = [R['o64c16']['post'], R['o64c64']['post'], R['o64c256']['post']]
        oc = max(x['post'] for x in o) - min(x['post'] for x in o); cc = max(c) - min(c)
        expect('B3f: heap does not move with the constant (range over constants < 0.25 x range over options)', cc < 0.25 * oc, 'constants %s range %d; options range %d' % (c, cc, oc))
        s = [R[a]['si'] for a in ('o64c16', 'o64c64', 'o64c256')]
        expect('B3f: SI bytes nearly flat across constants (within 5 percent)', (max(s) - min(s)) / min(s) <= 0.05, '%s spread %.2f%%' % (s, 100 * (max(s) - min(s)) / min(s)))
        sg = [R[a]['seg'] for a in ('o64c16', 'o64c64', 'o64c256')]
        print('INFO segments across constants at option 64: %s' % sg)
    sO = [R[a]['si'] for a in ('o8c64', 'o64c64', 'o512c64')]
    print('INFO SI bytes across options 8/64/512 (segment-count overhead only): %s' % sO)
if 'pfx64' in R and 'o64c64' in R:
    print('INFO PREFIX control: SI %s vs SPARSE %s, postGC %d vs %d MiB, segments %d vs %d' % (R['pfx64']['si'], R['o64c64']['si'], R['pfx64']['post'], R['o64c64']['post'], R['pfx64']['seg'], R['o64c64']['seg']))
print('SUMMARY expectations pass=%d fail=%d' % (ok, fail))
