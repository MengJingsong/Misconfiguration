#!/usr/bin/env python3
"""B20 per-lifetime summary: summarize.py <run dir> [...]. result.txt; baseline used (jcmd before the trigger); peak
sampled heap used and RssAnon after the trigger; GC log: pauses after the trigger, max post-GC heap after the trigger,
last pause; last 'Secondary index build' progress from nodetool compactionstats; hprof B20 line and the top frames of the
first stack with SecondaryIndexManager; gcwin."""
import datetime, glob, os, re, sys
def epoch(iso):  # 2026-11-21T06:31:02.123-0700
    return datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
for rd in sys.argv[1:]:
    rp = os.path.join(rd, 'result.txt'); res = open(rp).read() if os.path.exists(rp) else ''
    print(f'=== {os.path.basename(rd)}'); print(res.strip())
    kv = dict(re.findall(r'^(\w+)=(\S+)', res, re.M)); T0 = float(kv.get('trigger_epoch', '0') or 0)
    b = open(os.path.join(rd, 'baseline.txt')).read() if os.path.exists(os.path.join(rd, 'baseline.txt')) else ''
    m = re.search(r'total (\d+)K, used (\d+)K', b); base = int(m.group(2)) / 1024 if m else None
    peak = 0; rss = 0
    if os.path.exists(os.path.join(rd, 'heap.csv')):
        for line in open(os.path.join(rd, 'heap.csv')):
            t = float(line.split('|')[0])
            if t < T0: continue
            m = re.search(r'used (\d+)K', line); peak = max(peak, int(m.group(1)) / 1024) if m else peak
            m = re.search(r'rssAnonKB=(\d+)', line); rss = max(rss, int(m.group(1)) / 1024) if m else rss
    pauses = []; full = 0
    pat = re.compile(r'^\[([0-9T:.\-+]+)\].*Pause (\S+).* (\d+)M->(\d+)M\((\d+)M\) ([0-9.]+)ms')
    for f in sorted(glob.glob(os.path.join(rd, 'logs', 'gc.log*'))):
        for line in open(f, errors='replace'):
            m = pat.search(line)
            if m and epoch(m.group(1)) >= T0:
                pauses.append((epoch(m.group(1)) - T0, m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), float(m.group(6))))
                if m.group(2) == 'Full': full += 1
    mx = max((p[3] for p in pauses), default=None)
    print(f'baseline_used={base and round(base)} MiB  peak_sampled_used_after_trigger={peak:.0f} MiB  peak_rssAnon_after_trigger={rss:.0f} MiB')
    print(f'gc_after_trigger: pauses={len(pauses)} full={full} max_post_gc={mx} MiB last={pauses[-1] if pauses else None}')
    last = None
    if os.path.exists(os.path.join(rd, 'cstats.log')):
        ts = None
        for line in open(os.path.join(rd, 'cstats.log')):
            if line.startswith('=== '): ts = float(line.split()[1]); continue
            m = re.search(r'Secondary index build\s+ks\s+t\s+(\d+)\s+(\d+)\s+bytes', line)
            if m: last = (round(ts - T0, 1), int(m.group(1)), int(m.group(2)))
    if last: print(f'last_index_build_progress: t+{last[0]}s completed={last[1]} total={last[2]} ({100*last[1]/last[2]:.1f}%)')
    p = os.path.join(rd, 'hprofhist.txt')
    if os.path.exists(p):
        for line in open(p):
            if line.startswith(('B20', 'total shallow', 'org.apache.cassandra.db.rows.BTreeRow', 'java.nio.HeapByteBuffer',
                                'org.apache.cassandra.db.rows.BufferCell', 'org.apache.cassandra.db.partitions.ImmutableBTreePartition')):
                print('hprof: ' + line.rstrip())
    p = os.path.join(rd, 'hprofstacks.txt')
    if os.path.exists(p):
        parts = open(p).read().split('--- thread')
        if len(parts) > 1: print('stack (first with SecondaryIndexManager):\n--- thread' + '\n'.join(parts[1].splitlines()[:30]))
    p = os.path.join(rd, 'gcwin.txt')
    if os.path.exists(p): print('gcwin: ' + open(p).read().strip())
