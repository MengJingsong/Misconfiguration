"""Stage-4 harness: summary of one cluster-tier run (B3, amended 2026-10-24) of
memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.
usage: python3 -I summarize.py <run-log-dir> <threshold>"""
import os, re, statistics, sys
d, t = sys.argv[1], float(sys.argv[2])
MiB = 1048576
def rd(n):
    p = os.path.join(d, n)
    return open(p, errors='replace').read() if os.path.exists(p) else ''
print('threshold', t)
print('config_readback:'); print(rd('config-readback.txt').rstrip())
hs = re.search(r'memtable_heap_space=(\d+)MiB', rd('config-readback.txt'))
limit_mib = int(hs.group(1)) if hs else None
print('limit_MiB', limit_mib)
if os.path.exists(os.path.join(d, 'startfail.txt')):
    print('startfail:'); print(rd('startfail.txt').rstrip()); sys.exit(0)
marks = {}
for l in rd('markers.txt').splitlines():
    k, ms, off = l.split(); marks[k] = (int(ms), int(off))
FL = re.compile(r"Flushing largest CFS\(Keyspace='keyspace1', ColumnFamily='standard1'\) to free up room\. Used total: ([\d.]+)/([\d.]+), "
                r"live: ([\d.]+)/([\d.]+), flushing: ([\d.]+)/([\d.]+), this: ([\d.]+)/([\d.]+)")
ANYFL = re.compile(r"Flushing largest (\S+.*?) to free up room\. Used total: ([\d.]+)/")
ENQ = re.compile(r"Enqueuing flush of (\S+), Reason: (\w+)")
rows = [l.split(',') for l in rd('samples.csv').splitlines()[1:]]
ok = [r for r in rows if len(r) == 5 and r[1].isdigit()]
print('samples', len(rows), 'valid', len(ok))
def phase(name, a, b):
    txt = rd('flush-lines-%s.txt' % name)
    if not txt and name == 'p1': return
    fl = [tuple(float(x) for x in m.groups()) for m in map(FL.search, txt.splitlines()) if m]
    other = [m.group(1) for m in map(ANYFL.search, txt.splitlines()) if m and 'keyspace1' not in m.group(1)]
    reasons = {}
    for m in map(ENQ.search, txt.splitlines()):
        if m: reasons.setdefault(m.group(1), {}).setdefault(m.group(2), 0); reasons[m.group(1)][m.group(2)] += 1
    ks = reasons.get('keyspace1.standard1', {})
    print('== phase', name)
    print(' flushing_largest_lines_keyspace1', len(fl), 'other_tables', len(other))
    print(' enqueuing_reasons', reasons)
    print(' ks_MEMTABLE_LIMIT', ks.get('MEMTABLE_LIMIT', 0), 'ks_COMMITLOG_DIRTY', ks.get('COMMITLOG_DIRTY', 0),
          'ks_MEMTABLE_PERIOD_EXPIRED', ks.get('MEMTABLE_PERIOD_EXPIRED', 0),
          'limit_enq_over_lines %.3f' % (ks.get('MEMTABLE_LIMIT', 0) / len(fl) if fl else float('nan')))
    if fl:
        used = [f[0] for f in fl]; flushing = [f[4] for f in fl]; live = [f[2] for f in fl]
        print(' used_total median %.3f min %.2f max %.2f' % (statistics.median(used), min(used), max(used)))
        print(' live median %.3f max %.2f; flushing median %.3f max %.2f' % (statistics.median(live), max(live), statistics.median(flushing), max(flushing)))
        frac = sum(u - f >= t - 0.01 - 1e-9 for u, f in zip(used, flushing)) / len(fl)
        print(' frac_used_minus_flushing_ge_t-0.01 %.3f' % frac)
        i = max(range(len(fl)), key=lambda k: (used[k], flushing[k]))
        print(' max_used_line used %.2f flushing %.2f live %.2f' % (used[i], flushing[i], live[i]))
        passing = [(u, f) for u, f in zip(used, flushing) if u >= t + 0.10 - 1e-9 and f >= 0.10 - 1e-9]
        print(' lines_used_ge_t+0.10_with_flushing_ge_0.10', len(passing), 'max_flushing_any_line %.2f' % max(flushing))
        print(' lines_used_gt_1.02', sum(u > 1.02 + 1e-9 for u in used), 'lines_used_ge_0.90', sum(u >= 0.90 - 1e-9 for u in used))
        if limit_mib: print(' pool_peak_MiB %.1f' % (max(used) * limit_mib))
    s = [r for r in ok if a <= int(r[0]) <= b]
    if s:
        g = [int(r[1]) for r in s]; bl = [int(r[2]) for r in s]; pe = [int(r[3]) for r in s]; hu = [int(r[4]) for r in s]
        print(' gauge samples %d median_MiB %.2f peak_MiB %.2f' % (len(g), statistics.median(g) / MiB, max(g) / MiB))
        print(' blocked first %d last %d delta %d; pending_flush_tasks max %d; heap_used max_MiB %.1f' % (bl[0], bl[-1], bl[-1] - bl[0], max(pe), max(hu) / MiB))
    st = rd('stress-%s.log' % name)
    for k in ('Op rate', 'Partition rate', 'Total partitions', 'Total errors', 'Total operation time'):
        m = re.search(r'^%s\s*:\s*(.*)$' % k, st, re.M); print(' stress', k, ':', m.group(1).strip() if m else None)
if 'p1start' in marks: phase('p1', marks['p1start'][0], marks['p2start'][0])
if 'p2start' in marks: phase('p2', marks['p2start'][0], marks['p2cut'][0])
sj = rd('sjk-blocked-end.txt').strip().splitlines()
print('sjk_blocked_end', sj[-1] if sj else None, '| sampler_blocked_last', ok[-1][2] if ok else None)
print('oom_count', rd('oom-count.txt').strip(), 'error_warn_lines', len(rd('error-warn.txt').splitlines()))
print('commands_tail:'); print('\n'.join(rd('commands.log').splitlines()[-5:]))
