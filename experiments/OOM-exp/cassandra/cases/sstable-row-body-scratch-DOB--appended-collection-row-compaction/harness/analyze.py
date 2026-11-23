#!/usr/bin/env python3
# U12 per-run summary: analyze.py <run-dir>
# Reads samples.csv (O1, 250 ms), rss.csv (O2), progress.txt (compaction start epoch), logs/system.log (O4).
# Line 1: one-line outcome. Then the direct-memory steps (distinct direct_used levels over baseline, >= 8 MiB apart).
import sys, os, re, csv, statistics
R = sys.argv[1]; MiB = 1048576.0
prog = open(os.path.join(R, 'progress.txt')).read()
m = re.search(r'\] (\d+) compaction started', prog); tc = int(m.group(1)) if m else None
import datetime
_sl = open(os.path.join(R, 'logs', 'system.log'), errors='replace').read() if os.path.exists(os.path.join(R, 'logs', 'system.log')) else ''
_mc = re.search(r'\[CompactionExecutor:\d+\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3}) CompactionTask.java:\d+ - Compacting \([^)]*\) \[[^\]]*/u12/t-', _sl)
if _mc:  # log timestamps are UTC on ms0611
    tc = int(datetime.datetime.strptime(_mc.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp() * 1000) + int(_mc.group(2))
rows = list(csv.DictReader(open(os.path.join(R, 'samples.csv'))))
def f(r, k):
    try:
        v = float(r[k]); return v if v >= 0 else None
    except Exception: return None
good = [r for r in rows if f(r, 'direct_used') is not None]
pre = [f(r, 'direct_used') for r in good if tc and int(r['epoch_ms']) < tc]
base = statistics.median(pre[-20:]) if pre else (f(good[0], 'direct_used') if good else 0)
post = [r for r in good if not tc or int(r['epoch_ms']) >= tc]
pk = lambda k, rs: max([(f(r, k) or 0) for r in rs] or [0])
lastgood = int(good[-1]['epoch_ms']) if good else None
dead = next((int(r['epoch_ms']) for r in rows if r['direct_used'] == 'NA' and lastgood and int(r['epoch_ms']) > lastgood), None)
rss = list(csv.DictReader(open(os.path.join(R, 'rss.csv')))) if os.path.exists(os.path.join(R, 'rss.csv')) else []
rsspk = max([float(r['rss_anon_kb']) for r in rss if r.get('rss_anon_kb')] or [0]) / 1024
hwm = max([float(r['vmhwm_kb']) for r in rss if r.get('vmhwm_kb')] or [0]) / 1024
sl = open(os.path.join(R, 'logs', 'system.log'), errors='replace').read() if os.path.exists(os.path.join(R, 'logs', 'system.log')) else ''
lines = sl.splitlines()
first = None
for i, l in enumerate(lines):
    if 'OutOfMemoryError' in l and 'JVM Arguments' not in l:
        first = i; break
oom = 'none'; thread = ''; stk = ''
if first is not None:
    blk = lines[first:first + 45]
    msg = next((x for x in blk if 'java.lang.OutOfMemoryError' in x), blk[0])
    oom = 'direct' if 'Direct buffer memory' in msg else ('heap' if 'Java heap space' in msg else msg.strip()[:80])
    mt = re.search(r'(?:ERROR|WARN|INFO)\s+\[([^\]]+)\]', lines[first]) or re.search(r'(?:ERROR|WARN|INFO)\s+\[([^\]]+)\]', lines[first - 1]); thread = mt.group(1) if mt else '?'
    s = '\n'.join(blk)
    stk = ','.join(k for k in ['expandToFit', 'UnfilteredSerializer.serialize', 'SortedTablePartitionWriter.addUnfiltered', 'CompactionTask'] if k in s)
compacted = re.search(r'Compacted \([^)]*\) (\d+) sstables to \[[^\]]*/data/u12/t-[^\]]*\] to level=\d+\.\s+(\S+) to (\S+) \(', sl)
cmsg = ('compacted %s sstables %s -> %s' % compacted.groups()) if compacted else 'no-compacted-line'
mm = re.search(r'MaxDirectMemorySize=(\S+)', open(os.path.join(R, 'cmdline.txt')).read()) if os.path.exists(os.path.join(R, 'cmdline.txt')) else None
print('oom=%s thread=%s stack=[%s] | base_direct=%.1f peak_direct_used=%.1f peak_direct_cap=%.1f peak_heap=%.1f MiB rss_anon_peak=%.0f vmhwm=%.0f MiB | death_after_cmp_start_s=%s | %s | MaxDirectMemorySize=%s' % (
    oom, thread, stk, base / MiB, pk('direct_used', post) / MiB, pk('direct_capacity', post) / MiB, pk('heap_used', good) / MiB, rsspk, hwm,
    ('%.1f' % ((dead - tc) / 1000.0)) if (dead and tc) else 'NA', cmsg, mm.group(1) if mm else '?'))
# direct steps
lev = []; last = None
for r in post:
    v = (f(r, 'direct_used') - base) / MiB
    if last is None or abs(v - last) >= 8:
        lev.append('%+.1fs:%.0f' % ((int(r['epoch_ms']) - (tc or 0)) / 1000.0, v)); last = v
print('direct_used-over-base steps (s after cmp start: MiB):', ' '.join(lev[:80]))
