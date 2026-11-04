#!/usr/bin/env python3
"""Readings of the cluster tier of one EXCESS_WASTE_* case: python3 analyze_cluster.py <case 1|2|3|4|all> [logs-dir]
One block per cell (~/stage4-logs/ew/cluster/<tag>/): validity (S5), per-flush quantities of ks.t from debug.log (leaving out the first
and the last flush), the S4 counters (last line of s4waste.csv), the TRACE contention lines, the JMX samples (peak MemtableOnHeapSize,
AllMemtablesHeapSize, last MemtableSwitchCount, LiveDiskSpaceUsed), the allocation volume computed from gc.log (sum of before_i - after_(i-1)
over all pauses), BLOCKED threads and frames in the thread dumps. Then the group comparisons by the S5 rules (medians; factor 1.3)."""
import glob, os, re, statistics, sys

case = sys.argv[1]; D = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/stage4-logs/ew/cluster')
UNIT = {'B': 1, 'KiB': 1024, 'MiB': 1 << 20, 'GiB': 1 << 30}
W = re.compile(r'Writing Memtable-t@\d+\(([\d.]+)(B|KiB|MiB|GiB) serialized bytes, (\d+) ops, ([\d.]+)(B|KiB|MiB|GiB) \((\d+)%\) on-heap, ([\d.]+)(B|KiB|MiB|GiB) \((\d+)%\) off-heap')
E = re.compile(r'Enqueuing flush of ks\.t, Reason: (\w+), Usage: ([\d.]+)(B|KiB|MiB|GiB) \((\d+)%\) on-heap, ([\d.]+)(B|KiB|MiB|GiB) \((\d+)%\) off-heap')
HC = re.compile(r'High update contention in (\d+)/(\d+) partitions')
GCL = re.compile(r'Pause (?:Young|Full|Mixed)[^\n]*? (\d+)([MGK])->(\d+)([MGK])\((\d+)([MGK])\) ([\d.]+)ms')
CELLS = {}


def b(x, u): return float(x) * UNIT[u]


def cell(tag):
    d = '%s/%s' % (D, tag); r = {'tag': tag}
    summ = open(d + '/summary.txt').read() if os.path.exists(d + '/summary.txt') else ''
    r['header'] = (re.search(r'=== \S+: (.*)', summ) or [None, '?'])[1]
    m = re.search(r'READBACK constant in the running node: EXCESS_WASTE_BYTES=(\d+) EXCESS_WASTE_OFFSET=(\d+)', summ); r['C'] = int(m.group(1)) if m else None
    m = re.search(r'LOADGEN-DONE requests=(\d+) rows=(\d+) errors=(\d+) payloadBytes=(\d+)', summ + (open(d + '/loadgen.out').read() if os.path.exists(d + '/loadgen.out') else ''))
    r['requests'], r['rows'], r['errors'], r['payload'] = (int(m.group(i)) for i in (1, 2, 3, 4)) if m else (0, 0, -1, 0)
    ld = [l.split(',') for l in open(d + '/load.csv')] if os.path.exists(d + '/load.csv') else []
    r['secs'] = (int(ld[-1][0]) - int(ld[0][0])) / 1000.0 if len(ld) > 1 else 0
    # flushes
    dbg = open(d + '/debug.log', errors='replace').read() if os.path.exists(d + '/debug.log') else ''
    fl = [(b(m.group(1), m.group(2)), int(m.group(3)), b(m.group(4), m.group(5)), b(m.group(7), m.group(8))) for m in W.finditer(dbg)]
    r['flushes_all'] = len(fl); fl = fl[1:-1] if len(fl) > 2 else []
    r['flushes'] = len(fl)
    r['ops_med'] = statistics.median([f[1] for f in fl]) if fl else 0
    r['ser_med'] = statistics.median([f[0] for f in fl]) if fl else 0
    r['onheap_med'] = statistics.median([f[2] for f in fl]) if fl else 0
    r['onheap_max'] = max([f[2] for f in fl]) if fl else 0
    sysl = open(d + '/system.log', errors='replace').read() if os.path.exists(d + '/system.log') else ''
    en = [(m.group(1), b(m.group(2), m.group(3)), b(m.group(5), m.group(6))) for m in E.finditer(dbg)]
    en = [e for e in en if e[0] != 'DRAIN' and e[0] != 'USER_FORCED']
    r['enq_n'] = len(en); r['enq_reasons'] = sorted({e[0] for e in en})
    r['enq_on_med'] = statistics.median([e[1] for e in en[1:]]) if len(en) > 1 else (en[0][1] if en else 0)
    hc = [(int(m.group(1)), int(m.group(2))) for m in HC.finditer(dbg)]
    r['hc_lines'] = len(hc); r['hc_parts'] = sum(x for x, y in hc); r['hc_of'] = sum(y for x, y in hc)
    # counters
    s4 = [l.strip().split(',') for l in open(d + '/s4waste.csv') if l[0].isdigit()] if os.path.exists(d + '/s4waste.csv') else []
    last = [int(x) for x in s4[-1]] if s4 else [0] * 10
    r['s4'] = dict(zip('ms attempts fails failHeap lockedAttempts lockedFails lockedFailHeap trackerCalls trackerBytes flips'.split(), last))
    # jmx samples: ts, AllMemtablesHeapSize, MemtableOnHeapSize, MemtableOffHeapSize, MemtableLiveDataSize, MemtableColumnsCount, MemtableSwitchCount, heap used, LiveDiskSpaceUsed
    sm = []
    if os.path.exists(d + '/samples.csv'):
        for l in open(d + '/samples.csv'):
            p = l.strip().split(',')
            if len(p) >= 9 and p[1] != 'ERR':
                try: sm.append([int(x) for x in p[:9]])
                except ValueError: pass
    r['samples'] = len(sm)
    if sm:
        r['peak_all'] = max(s[1] for s in sm); r['peak_on'] = max(s[2] for s in sm); r['peak_off'] = max(s[3] for s in sm)
        r['switches'] = sm[-1][6]; r['heap_peak'] = max(s[7] for s in sm); r['disk_live'] = sm[-1][8]
        on = sorted(s[2] for s in sm); r['on_p50'] = on[len(on) // 2]; r['on_p95'] = on[int(len(on) * .95)]
    # gc
    g = open(d + '/gc.log', errors='replace').read() if os.path.exists(d + '/gc.log') else ''
    def mb(x, u): return int(x) * {'K': 1 / 1024.0, 'M': 1, 'G': 1024}[u]
    pauses = [(mb(m.group(1), m.group(2)), mb(m.group(3), m.group(4)), float(m.group(7))) for m in GCL.finditer(g)]
    alloc = 0.0; prev_after = None
    for bf, af, ms in pauses:
        if prev_after is not None and bf >= prev_after: alloc += bf - prev_after
        prev_after = af
    r['gc_pauses'] = len(pauses); r['gc_alloc_mb'] = alloc; r['gc_full'] = len(re.findall(r'Pause Full', g)); r['gc_after_max_mb'] = max([p[1] for p in pauses] or [0])
    r['gc_maxpause_ms'] = max([p[2] for p in pauses] or [0])
    # threads
    bl = fr = 0
    for f in glob.glob(d + '/threads-*.txt'):
        t = open(f, errors='replace').read(); bl += len(re.findall(r'java.lang.Thread.State: BLOCKED', t)); fr += t.count('AtomicBTreePartition')
    r['blocked'] = bl; r['abtp_frames'] = fr
    du = [l.strip().split(',') for l in open(d + '/du.csv')] if os.path.exists(d + '/du.csv') else []
    r['min_free_gb'] = min([int(x[1]) for x in du] or [0]); r['max_data_commitlog'] = max([sum(int(y) for y in x[2:]) for x in du if len(x) > 2] or [0])
    # validity (S5)
    r['valid'] = (r['errors'] >= 0 and r['errors'] <= 0.01 * max(1, r['requests'] + r['errors']) and r['C'] is not None and r['s4']['attempts'] > 0 and r['flushes'] >= 4)
    return r


def show(r):
    s = r['s4']
    print('\n--- %s  [%s]' % (r['tag'], r['header']))
    print('  valid=%s  C=%s  load %.0f s: %d requests, %d rows (%.1f MiB payload) %.1f MB/s, errors %d' % (r['valid'], r['C'], r['secs'], r['requests'], r['rows'], r['payload'] / 1048576.0, r['payload'] / 1e6 / max(1, r['secs']), r['errors']))
    print('  flushes of ks.t: %d (%d used): ops/flush median %d, serialized median %.1f MiB, on-heap at Writing median %.1f MiB max %.1f MiB; Enqueuing flush n=%d reasons %s on-heap median %.1f MiB' % (
        r['flushes_all'], r['flushes'], r['ops_med'], r['ser_med'] / 1048576, r['onheap_med'] / 1048576, r['onheap_max'] / 1048576, r['enq_n'], r['enq_reasons'], r['enq_on_med'] / 1048576))
    print('  S4: attempts %d fails %d (%.1f%%) failHeap %.1f MiB | locked attempts %d fails %d | tracker calls %d | flips %d | TRACE contention lines %d (%d of %d partitions)' % (
        s['attempts'], s['fails'], 100.0 * s['fails'] / max(1, s['attempts']), s['failHeap'] / 1048576, s['lockedAttempts'], s['lockedFails'], s['trackerCalls'], s['flips'], r['hc_lines'], r['hc_parts'], r['hc_of']))
    if r.get('samples'):
        print('  JMX (%d samples): MemtableOnHeapSize peak %.1f MiB p95 %.1f MiB p50 %.1f MiB; AllMemtablesHeapSize peak %.1f MiB; off-heap peak %.1f MiB; switch count %d; heap used peak %.0f MiB; LiveDiskSpaceUsed %.1f MiB' % (
            r['samples'], r['peak_on'] / 1048576, r['on_p95'] / 1048576, r['on_p50'] / 1048576, r['peak_all'] / 1048576, r['peak_off'] / 1048576, r['switches'], r['heap_peak'] / 1048576, r['disk_live'] / 1048576))
    print('  GC: %d pauses, %d Full, allocation volume %.0f MB (%.1f MB/s), heap after GC max %.0f MB, max pause %.0f ms | threads: BLOCKED %d, AtomicBTreePartition frames %d | min free disk %d GB, max data+commitlog %.0f MiB' % (
        r['gc_pauses'], r['gc_full'], r['gc_alloc_mb'], r['gc_alloc_mb'] / max(1, r['secs']), r['gc_after_max_mb'], r['gc_maxpause_ms'], r['blocked'], r['abtp_frames'], r['min_free_gb'], r['max_data_commitlog'] / 1048576))


def group(title, tags, metric_names=('ops_med', 'onheap_med', 'enq_on_med', 'peak_on', 'gc_alloc_mb')):
    rs = [CELLS[t] for t in tags if t in CELLS]
    if not rs: return
    print('\n=== group %s' % title)
    for m in metric_names:
        vals = [(r['tag'], r.get(m, 0)) for r in rs]
        pos = [v for t, v in vals if v > 0]
        ratio = max(pos) / min(pos) if len(pos) > 1 else float('nan')
        print('  %-12s %s  max/min=%.2f %s' % (m, ' '.join('%s=%.4g' % (t.split('-', 1)[1], v) for t, v in vals), ratio, '(<=1.3 flat)' if ratio <= 1.3 else '(>1.3)'))


tags = sorted(os.path.basename(p) for p in glob.glob(D + '/c%s*' % ('' if case == 'all' else case)) if os.path.isdir(p))
for t in tags:
    try:
        CELLS[t] = cell(t); show(CELLS[t])
    except Exception as e:
        print('\n--- %s: analysis error %r' % (t, e))
if case in ('1', 'all'):
    for v in ('v10m', 'v1', 'v2p40'):
        group('case 1, constant %s, repeats' % v, ['c1-%s-r%d' % (v, k) for k in (1, 2, 3)])
    for m in ('ops_med', 'onheap_med', 'enq_on_med', 'peak_on', 'gc_alloc_mb'):
        meds = {v: statistics.median([CELLS['c1-%s-r%d' % (v, k)][m] for k in (1, 2, 3) if 'c1-%s-r%d' % (v, k) in CELLS] or [0]) for v in ('v10m', 'v1', 'v2p40')}
        pos = [x for x in meds.values() if x > 0]
        print('  [S5 across constants] %-12s medians of repeats: %s  max/min=%.2f' % (m, {k: round(v, 3) for k, v in meds.items()}, (max(pos) / min(pos)) if len(pos) > 1 else float('nan')))
    group('case 1, pool control (v10m, WA)', ['c1-ctl128', 'c1-v10m-r1', 'c1-ctl1024'], ('enq_on_med', 'onheap_med', 'ops_med', 'peak_on'))
if case in ('2', 'all'):
    group('case 2, WB hot: constant 1 MiB / 10 MiB / 100 MiB', ['c2-hot-v1m', 'c2-hot', 'c2-hot-v100m'])
    group('case 2, pool 128 vs 512: hot', ['c2-hot128', 'c2-hot'], ('enq_on_med', 'onheap_med', 'ops_med', 'peak_on'))
    group('case 2, pool 128 vs 512: cold', ['c2-cold128', 'c2-cold'], ('enq_on_med', 'onheap_med', 'ops_med', 'peak_on'))
if case in ('3', 'all'):
    for w in ('WD', 'WE'):
        for m in ('ops_med', 'onheap_med', 'enq_on_med', 'peak_on', 'gc_alloc_mb'):
            meds = {v: statistics.median([CELLS['c3-%s-%s-r%d' % (w, v, k)][m] for k in (1, 2) if 'c3-%s-%s-r%d' % (w, v, k) in CELLS] or [0]) for v in ('v1m', 'v10m', 'v1g')}
            pos = [x for x in meds.values() if x > 0]
            print('  [S5 across constants] %s %-12s medians of repeats: %s  max/min=%.2f' % (w, m, {k: round(v, 3) for k, v in meds.items()}, (max(pos) / min(pos)) if len(pos) > 1 else float('nan')))
    group('case 3, pool 128 vs 512 (WD, v10m)', ['c3-ctl128', 'c3-WD-v10m-r1', 'c3-WD-v10m-r2'], ('enq_on_med', 'onheap_med', 'ops_med', 'peak_on'))
if case in ('4', 'all'):
    for w in ('WF', 'WG'):
        group('case 4, %s: constants v10m / v1g / v1024' % w, ['c4-%s-v10m' % w, 'c4-%s-v1g' % w, 'c4-%s-v1024' % w])
    group('case 4, pool 128 / 512 / 1024 (WF, v10m)', ['c4-ctl128', 'c4-WF-v10m', 'c4-ctl1024'], ('enq_on_med', 'onheap_med', 'ops_med', 'peak_on'))
