"""Stage-4 harness: summary of one cluster-tier run (B3, amended 2026-10-24) of
memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.  usage: python3 -I summarize.py <run-log-dir>"""
import os, re, statistics, sys
d = sys.argv[1]
def rd(n):
    p = os.path.join(d, n)
    return open(p, errors='replace').read() if os.path.exists(p) else ''
MiB = 1048576
st = rd('startup-threshold.txt')
print('startup_lines:'); print(st.strip())
m = re.search(r'off-heap threshold is enabled at (\d+)MiB', st)
knob = int(m.group(1)) if m else None
print('offheap_knob_MiB(startup log)', knob, '| line592_disabled_message', 'off-heap threshold is disabled, HeapAllocator will be used instead' in st)
print(rd('startup.txt').strip())
td = rd('threaddump.txt')
if td:
    blocks = re.split(r'\n(?=")', td)
    waiting = [b.split('\n', 1)[0] for b in blocks if 'MemtableAllocator$SubAllocator.allocate' in b]
    print('threaddump_threads', len(blocks), 'threads_in_SubAllocator.allocate', len(waiting))
    for w in waiting[:5]: print('  ', w[:120])
rows = [l.split(',') for l in rd('samples.csv').splitlines()[1:]]
ok = [r for r in rows if len(r) >= 6 and r[1].isdigit()]
mk = dict(l.split() for l in rd('markers.txt').splitlines() if l.strip())
s0 = int(mk.get('stress_start', 0)); s1 = int(mk.get('stress_end', 0))
print('samples', len(rows), 'valid', len(ok), 'span_s', (int(ok[-1][0]) - int(ok[0][0])) / 1000 if ok else 0, '| stress_s', s1 - s0)
if ok:
    on = [int(r[1]) for r in ok]; off = [int(r[2]) for r in ok]; blk = [int(r[3]) for r in ok]; wc = [int(r[4]) for r in ok]
    print('onheap_gauge_peak_MiB %.2f median_MiB %.2f' % (max(on) / MiB, statistics.median(on) / MiB))
    print('offheap_gauge_peak_MiB %.2f median_MiB %.2f' % (max(off) / MiB, statistics.median(off) / MiB))
    print('blocked_count_first %d last %d' % (blk[0], blk[-1]))
    inwin = [int(r[4]) for r in ok if s0 * 1000 <= int(r[0]) <= (s1 + 10) * 1000]
    print('write_count_first %d last %d delta_in_stress_window %s' % (wc[0], wc[-1], (inwin[-1] - inwin[0]) if inwin else None))
    if knob:
        lim = knob * MiB * 1.05; run = best = 0
        for v in off:
            run = run + 1 if v > lim else 0; best = max(best, run)
        print('offheap_peak_over_knob_ratio %.3f samples_over_1.05knob %d longest_consecutive_over %d' % (max(off) / (knob * MiB), sum(v > lim for v in off), best))
fl = rd('flush-lines.txt').splitlines()
largest = [l for l in fl if 'Flushing largest' in l]; enq = [l for l in fl if 'Enqueuing flush' in l]
reasons = {}
for l in enq:
    r = re.search(r'Reason: (\w+)', l); k = r.group(1) if r else '?'; reasons[k] = reasons.get(k, 0) + 1
ut = [(float(a), float(b)) for l in largest for a, b in re.findall(r'Used total: ([0-9.]+)/([0-9.]+)', l)]
print('flushing_largest_lines', len(largest), 'enqueuing_by_reason', dict(sorted(reasons.items())))
print('enqueuing_MEMTABLE_LIMIT_keyspace1', sum('keyspace1' in l and 'MEMTABLE_LIMIT' in l for l in enq))
if ut:
    offr = [b for a, b in ut]; onr = [a for a, b in ut]
    print('used_total_offheap_ratio max %.2f median %.2f min %.2f | onheap_ratio max %.2f | triggers_led_by_offheap %d of %d'
          % (max(offr), statistics.median(offr), min(offr), max(onr), sum(b >= a for a, b in ut), len(ut)))
    if knob: print('used_total_offheap_max_MiB %.1f' % (max(offr) * knob))
rs = [l.split(',') for l in rd('rss.csv').splitlines()[1:] if l.count(',') == 1 and l.split(',')[1].isdigit()]
if rs and s0:
    pre = [int(b) for a, b in rs if int(a) < s0]; dur = [int(b) for a, b in rs if s0 <= int(a) <= s1 + 10]
    if pre and dur:
        print('rss_pre_stress_MiB %.1f rss_peak_in_stress_MiB %.1f rss_growth_MiB %.1f rss_samples %d'
              % (pre[-1] / 1024, max(dur) / 1024, (max(dur) - pre[-1]) / 1024, len(rs)))
nm = rd('nmt.txt')
oth = [int(x) for x in re.findall(r'Other \(reserved=\d+KB, committed=(\d+)KB', nm)]
itn = [int(x) for x in re.findall(r'Internal \(reserved=\d+KB, committed=(\d+)KB', nm)]
tot = [int(x) for x in re.findall(r'Total: reserved=\d+KB, committed=(\d+)KB', nm)]
if tot: print('nmt_samples %d total_committed_MiB first %.1f max %.1f | other_committed_MiB first %.1f max %.1f | internal_MiB max %.1f'
              % (len(tot), tot[0] / 1024, max(tot) / 1024, (oth[0] / 1024) if oth else -1, (max(oth) / 1024) if oth else -1, (max(itn) / 1024) if itn else -1))
sj = rd('sjk-blocked-end.txt').strip().splitlines()
print('sjk_blocked_end', sj[-1] if sj else None, '| sjk_offheap_start', (rd('sjk-start.txt').strip().splitlines() or [None])[-1], '| sjk_offheap_end', (rd('sjk-end.txt').strip().splitlines() or [None])[-1])
s = rd('stress.log')
for k in ('Op rate', 'Partition rate', 'Total partitions', 'Total errors', 'Total operation time'):
    r = re.search(r'^%s\s*:\s*(.*)$' % k, s, re.M); print('stress', k, ':', r.group(1).strip() if r else None)
print('oom_count', len(re.findall('java.lang.OutOfMemoryError', rd('system.log'))), 'error_warn_lines', len(rd('error-warn.txt').splitlines()))
print('commands_tail:'); print('\n'.join(rd('commands.log').splitlines()[-6:]))
