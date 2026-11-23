#!/usr/bin/env python3
"""U13 per-run summary. usage: analyze.py <run dir> [steps]
Prints: resolved MaxDirectMemorySize/heap, load summary, u13.t flushes (rows, windows, overlap), direct pool baseline B0
(before the first u13.t flush), peak direct (MemoryUsed) with time, direct steps >= 8 MiB (whole-buffer check), NMT
'Other' at peak, System.gc() full GCs in gc.log, first OutOfMemoryError with thread and the next stack lines."""
import json, os, re, sys, time
from datetime import datetime, timezone

run = sys.argv[1]
L = os.path.join(run, 'logs')
MiB = 2 ** 20


def ts(ms):
    return time.strftime('%H:%M:%S', time.gmtime(ms / 1000.0)) + ('.%01d' % ((ms % 1000) // 100))


def logtime(s):
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d+)', s)
    if not m:
        return None
    d = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000) + int(m.group(2))


out = []
fl = open(os.path.join(L, 'vmflags.txt')).read() if os.path.exists(os.path.join(L, 'vmflags.txt')) else ''
md = re.search(r'MaxDirectMemorySize=(\d+)', fl); mh = re.search(r'MaxHeapSize=(\d+)', fl)
print('resolved MaxDirectMemorySize=%s MiB MaxHeapSize=%s MiB' % (int(md.group(1)) // MiB if md else '?', int(mh.group(1)) // MiB if mh else '?'))
try:
    print('load', open(os.path.join(L, 'load.json')).read().strip())
except Exception:
    print('load json missing')
# flushes
sl = os.path.join(L, 'system.log')
writes, dones = [], []
oom = None
lines = open(sl, errors='replace').read().splitlines() if os.path.exists(sl) else []
for i, l in enumerate(lines):
    if 'Writing Memtable-t@' in l:
        m = re.search(r'^\w+\s+\[([^\]]+)\].*\(([0-9.]+\w+) serialized bytes, (\d+) ops, ([0-9.]+\w+) \((\d+)%\) on-heap', l)
        writes.append((logtime(l), m.group(1), m.group(2), int(m.group(3)), m.group(4)))
    elif 'Completed flushing' in l and '/u13/t-' in l:
        m = re.search(r'^\w+\s+\[([^\]]+)\]', l)
        dones.append((logtime(l), m.group(1)))
    if oom is None and 'java.lang.OutOfMemoryError' in l and 'JVM Arguments' not in l:
        oom = (i, l)
print('u13.t flushes: %d started, %d completed' % (len(writes), len(dones)))
open_by_thread = {}
for w in writes:
    print('  start %s %-32s %10s serialized %7d rows on-heap %s' % (ts(w[0]), w[1], w[2], w[3], w[4]))
for d in dones:
    print('  done  %s %s' % (ts(d[0]), d[1]))
# poll
pl = os.path.join(L, 'poll.log')
rows = []
if os.path.exists(pl):
    f = open(pl).read().splitlines()
    h = f[0].split(); ix = {k: i for i, k in enumerate(h)}
    for r in f[1:]:
        p = r.split()
        if len(p) == len(h) and p[0].isdigit():
            rows.append(p)
if rows:
    t_first = writes[0][0] if writes else None
    pre = [int(r[ix['direct_used']]) for r in rows if t_first is None or int(r[0]) < t_first]
    b0 = pre[-1] if pre else None
    pk = max(rows, key=lambda r: int(r[ix['direct_used']]))
    print('B0 (direct_used just before first u13.t flush) = %s MiB' % (round(b0 / MiB, 1) if b0 is not None else '?'))
    print('peak direct_used = %.1f MiB at %s (count %s); last sample %s %.1f MiB' % (
        int(pk[ix['direct_used']]) / MiB, ts(int(pk[0])), pk[ix['direct_count']], ts(int(rows[-1][0])), int(rows[-1][ix['direct_used']]) / MiB))
    if len(sys.argv) > 2:
        prev = None
        for r in rows:
            d = int(r[ix['direct_used']])
            if prev is not None and abs(d - prev) >= 8 * MiB:
                print('  step %s %+8.1f MiB -> %7.1f MiB count %s  t_onheap %.0f MiB sw %s pend %s old_n %s' % (
                    ts(int(r[0])), (d - prev) / MiB, d / MiB, r[ix['direct_count']], int(r[ix['t_onheap']]) / MiB, r[ix['t_switch']],
                    r[ix['t_pendflush']], r[ix['G1_Old_Generation_n']]))
            prev = d
    print('heap_used max %.0f MiB; old GCs %s' % (max(int(r[ix['heap_used']]) for r in rows) / MiB, rows[-1][ix['G1_Old_Generation_n']]))
# NMT
nl = os.path.join(run, 'nmt', 'nmt.log')
if os.path.exists(nl):
    cur = None; best = (0, None)
    for l in open(nl):
        if l.startswith('@@'):
            cur = float(l.split()[1])
        m = re.search(r'Other \(reserved=(\d+)KB, committed=(\d+)KB', l)
        if m and cur:
            v = int(m.group(2)) // 1024
            if v > best[0]:
                best = (v, cur)
    if best[1]:
        print('NMT Other max committed = %d MiB at %s' % (best[0], ts(int(best[1] * 1000))))
# GC log: System.gc()
gl = os.path.join(L, 'gc.log')
if os.path.exists(gl):
    sg = [l.strip()[:160] for l in open(gl, errors='replace') if 'System.gc()' in l and 'Pause Full' in l]
    print('System.gc() full GCs: %d' % len(sg))
    for s in sg[:4]:
        print('  ' + s)
if oom:
    i, l = oom
    print('FIRST OOM (system.log line %d): %s' % (i + 1, l[:220]))
    for k in range(i + 1, min(i + 26, len(lines))):
        print('   ' + lines[k][:200])
else:
    so = os.path.join(L, 'stdout.txt')
    if os.path.exists(so):
        s = [l for l in open(so, errors='replace') if 'OutOfMemoryError' in l and 'JVM Arguments' not in l and 'HeapDumpOnOutOfMemoryError' not in l]
        print('stdout OOM lines: %d %s' % (len(s), s[:2]))
    print('no OutOfMemoryError in system.log')
