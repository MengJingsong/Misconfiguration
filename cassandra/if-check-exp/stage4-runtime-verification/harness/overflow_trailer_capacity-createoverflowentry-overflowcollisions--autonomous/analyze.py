#!/usr/bin/env python3
"""Readings of the overflow_trailer_capacity cluster tier. usage: analyze.py <cluster dir> (one directory per arm).
Prints a table and EXPECTED lines for B3f (frozen before the run) and amendments C1-C4."""
import os, re, sys, datetime
d = sys.argv[1]
def rd(p): return open(p, errors='replace').read() if os.path.exists(p) else ''
def arms(): return [a for a in ['g8', 'g9', 'g0', 'r1e5', 'r1e6', 'm1', 'm100'] if os.path.isdir('%s/%s' % (d, a))]
def ls_files(a):
    r = {}
    for l in rd('%s/%s/ls-sstable-dir.txt' % (d, a)).splitlines()[1:]:
        p = l.split()
        if len(p) >= 9: r[p[8]] = int(p[4])
    return r
def si_bytes(a): return sum(v for k, v in ls_files(a).items() if re.search(r'SI_', k))
def data_bytes(a): return sum(v for k, v in ls_files(a).items() if k.endswith('-Data.db'))
def window(a):
    t = rd('%s/%s/windows.txt' % (d, a)); s = re.search(r'COMPACT_START (\d+)', t); e = re.search(r'COMPACT_END (\d+)', t)
    return (int(s.group(1)), int(e.group(1))) if s and e else None
def gcmax(a, lo=None, hi=None):
    best = 0
    for l in rd('%s/%s/gc.log' % (d, a)).splitlines():
        if 'Pause' not in l: continue
        m = re.search(r'(\d+)M->(\d+)M\(', l); t = re.match(r'\[(\d{4}-[^\]]+)\]', l)
        if not m or not t: continue
        if lo is not None:
            ts = datetime.datetime.strptime(t.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp() * 1000
            if ts < lo or ts > hi: continue
        best = max(best, int(m.group(2)))
    return best
def heapmax(a, lo=None, hi=None):
    best = 0
    for l in rd('%s/%s/heap.csv' % (d, a)).splitlines()[1:]:
        p = l.split(',')
        if len(p) > 1 and p[0].strip().isdigit() and p[1].strip().isdigit():
            if lo is not None and not (lo <= int(p[0]) <= hi): continue
            best = max(best, int(p[1]))
    return best
def segments(a, w):
    n = 0
    for l in rd('%s/%s/system.log' % (d, a)).splitlines():
        if 'Flushed index segment' not in l: continue
        m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d,\d+)', l)
        if m and w:
            ts = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000
            if w[0] <= ts <= w[1] + 2000: n += 1
        elif not w: n += 1
    return n
ok = fail = 0
def expect(name, cond, detail):
    global ok, fail
    if cond: ok += 1
    else: fail += 1
    print('EXPECTED %s: %s  %s' % (name, detail, 'PASS' if cond else 'FAIL'))
R = {}
for a in arms():
    w = window(a); bm = rd('%s/%s/byteman.txt' % (d, a)); sysl = rd('%s/%s/system.log' % (d, a))
    entries = [(int(m.group(1)), int(m.group(2))) for m in re.finditer(r'BM-OVF-ENTRY offsets=(\d+) slotsSoFar=(\d+)', bm)]
    R[a] = dict(si=si_bytes(a), data=data_bytes(a), entries=entries, throws=bm.count('BM-OVF-THROW'),
                msg=len(re.findall(r'cannot have more than 8 overflow collisions', sysl)),
                asserts=len(re.findall(r'AssertionError', sysl)), w=w,
                seg=segments(a, w) if w else None, post=gcmax(a, *w) if w else gcmax(a), heapw=heapmax(a, *w) if w else heapmax(a),
                files=sorted(ls_files(a)), ran='== %s end' % a in rd('%s/%s/cmdlog.txt' % (d, a)))
    r = R[a]
    print('%-5s SI=%s Data=%s ovfEntryCalls=%d throws=%d logMsg=%d AssertionErrorInLog=%d segments=%s postGCmaxMiB=%d sampledMaxMiB=%d' % (a, r['si'], r['data'], len(r['entries']), r['throws'], r['msg'], r['asserts'], r['seg'], r['post'], r['heapw'] / 1048576))
for a in ('g8', 'g0'):
    if a in R:
        r = R[a]; tg = rd('%s/%s/token-groups.txt' % (d, a)); ck = rd('%s/%s/collkeys.txt' % (d, a))
        expect('%s token(pk) on the node shows the intended groups' % a, (a == 'g0') or ('1000000007:4' in tg and '2000000014:4' in tg), tg.strip()[:90])
        expect('%s flush succeeds: a Data.db and a SI file exist' % a, r['data'] > 0 and r['si'] > 0, 'Data %d SI %d' % (r['data'], r['si']))
        expect('%s no throw (Byteman) and no overflow message in system.log' % a, r['throws'] == 0 and r['msg'] == 0, 'throws %d msg %d' % (r['throws'], r['msg']))
        if a == 'g8': expect('g8 Byteman saw 2 overflow entries of 4 offsets (8 slots in all)', sorted(r['entries']) == [(4, 0), (4, 4)], str(r['entries']))
if 'g9' in R:
    r = R['g9']
    expect('g9 Byteman saw the throw (disallow branch fired)', r['throws'] >= 1, 'throws %d, entries %s' % (r['throws'], r['entries']))
    expect('g9 the assertion message appears in system.log (B3f as filed)', r['msg'] >= 1, 'message lines %d, any AssertionError %d' % (r['msg'], r['asserts']))
    unopen = len(re.findall(r"Can't open index file .*SI_", rd('%s/g9/system.log' % d)))
    # instrument fix after the first g9 reading: a truncated SI file is left on disk, so 'no complete component' = no file, or a file the node cannot open
    expect('g9 no complete SI component for the flush (B3f): none, or one the node cannot open', r['si'] == 0 or unopen >= 1, 'SI bytes %d, node log cannot-open lines %d, files %s' % (r['si'], unopen, [f for f in r['files'] if 'SI' in f]))
    print('INFO g9 Data.db bytes %d (the base-table flush)' % r['data'])
    cl = []
    for l in rd('%s/g9/disk.csv' % d).splitlines()[1:]:
        p = l.split(',')
        if len(p) == 4: cl.append(int(p[2]))
    print('INFO g9 commit log bytes: min %d max %d last %d (samples %d)' % (min(cl), max(cl), cl[-1], len(cl)))
if 'g8' in R and 'g0' in R:
    expect('B3g: SI size at 8 slots within 64 bytes (8 x 8) of the 0-slot index', abs(R['g8']['si'] - R['g0']['si']) <= 64, 'g8 %d g0 %d' % (R['g8']['si'], R['g0']['si']))
if 'r1e5' in R and 'r1e6' in R:
    x = R['r1e6']['si'] / R['r1e5']['si']; y = R['r1e6']['data'] / R['r1e5']['data']
    expect('SI bytes grow with rows (1e6 / 1e5 between 5 and 15)', 5 <= x <= 15, '%.2f (%d / %d)' % (x, R['r1e6']['si'], R['r1e5']['si']))
    expect('Data.db grows with rows (1e6 / 1e5 between 5 and 15, positive control)', 5 <= y <= 15, '%.2f' % y)
if 'm1' in R and 'm100' in R:
    a, b = R['m1'], R['m100']
    expect('m1 writes more index segments than m100 (the option binds)', (a['seg'] or 0) > (b['seg'] or 0), 'm1 %s m100 %s' % (a['seg'], b['seg']))
    expect('B3f: peak heap in the compaction lower for the smaller option (max post-GC, MiB)', a['post'] < b['post'], 'm1 %d m100 %d' % (a['post'], b['post']))
    print('INFO sampled max heap used in the compaction window: m1 %.0f MiB, m100 %.0f MiB' % (a['heapw'] / 1048576, b['heapw'] / 1048576))
    print('INFO SI bytes m1 %d m100 %d (index-size effect of the option); Data.db m1 %d m100 %d' % (a['si'], b['si'], a['data'], b['data']))
print('SUMMARY expectations pass=%d fail=%d' % (ok, fail))
