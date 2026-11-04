"""Stage-4 harness: summary of one cluster-tier run (B3, amended 2026-10-24). usage: python3 -I summarize.py <run-log-dir>"""
import os, re, statistics, sys
d = sys.argv[1]
def rd(n):
    p = os.path.join(d, n)
    return open(p, errors='replace').read() if os.path.exists(p) else ''
MiB = 1048576
thr = re.search(r'on-heap threshold is enabled at (\d+)MiB', rd('startup-threshold.txt'))
knob = int(thr.group(1)) if thr else None
print('knob_MiB(startup log)', knob)
rows = [l.split(',') for l in rd('samples.csv').splitlines()[1:]]
ok = [r for r in rows if len(r) >= 4 and r[1].isdigit()]
on = [int(r[1]) for r in ok]; off = [int(r[2]) for r in ok]; blk = [int(r[3]) for r in ok]
print('samples', len(rows), 'valid', len(ok), 'span_s', (int(ok[-1][0]) - int(ok[0][0])) / 1000 if ok else 0)
if on:
    print('onheap_gauge_peak_MiB %.2f median_MiB %.2f' % (max(on) / MiB, statistics.median(on) / MiB))
    print('offheap_gauge_peak_MiB %.2f' % (max(off) / MiB))
    print('blocked_count_first %d last %d' % (blk[0], blk[-1]))
    if knob:
        lim = knob * MiB * 1.05; run = best = 0
        for v in on:
            run = run + 1 if v > lim else 0; best = max(best, run)
        print('peak_over_knob_ratio %.3f samples_over_1.05knob %d longest_consecutive_over %d' % (max(on) / (knob * MiB), sum(v > lim for v in on), best))
fl = rd('flush-lines.txt').splitlines()
largest = [l for l in fl if 'Flushing largest' in l]
enq = [l for l in fl if 'Enqueuing flush' in l]
reasons = {}
for l in enq:
    m = re.search(r'Reason: (\w+)', l); reasons[m.group(1) if m else '?'] = reasons.get(m.group(1) if m else '?', 0) + 1
used = [float(m.group(1)) for l in largest for m in [re.search(r'Used total: ([0-9.]+)/', l)] if m]
print('flushing_largest_lines', len(largest), 'enqueuing_by_reason', dict(sorted(reasons.items())))
print('enqueuing_MEMTABLE_LIMIT_keyspace1', sum('keyspace1' in l and 'MEMTABLE_LIMIT' in l for l in enq))
if used:
    print('used_total_onheap_ratio max %.2f min %.2f median %.2f' % (max(used), min(used), statistics.median(used)))
    if knob: print('used_total_onheap_max_MiB %.1f' % (max(used) * knob))
sj = rd('sjk-blocked-end.txt').strip().splitlines()
print('sjk_blocked_end', sj[-1] if sj else None, '| sjk_gauge_start', (rd('sjk-start.txt').strip().splitlines() or [None])[-1], '| sjk_gauge_end', (rd('sjk-end.txt').strip().splitlines() or [None])[-1])
og = [r for r in ok if len(r) == 7 and r[4].isdigit()]
if og:
    print('oldgen_used_max_MiB %.1f oldgen_after_gc_max_MiB %.1f heap_used_max_MiB %.1f oldgen_used_last_MiB %.1f' % (max(int(r[4]) for r in og) / MiB, max(int(r[5]) for r in og) / MiB, max(int(r[6]) for r in og) / MiB, int(og[-1][4]) / MiB))
js = rd('jstat-gc.txt').splitlines()
if js and 'OU' in js[0]:
    h = js[0].split(); iu = h.index('OU'); ic = h.index('OC')
    vals = [l.split() for l in js[1:] if len(l.split()) == len(h)]
    ou = [float(v[iu]) for v in vals]; oc = [float(v[ic]) for v in vals]
    if ou: print('jstat_rows', len(ou), 'OU_max_MiB %.1f OU_last_MiB %.1f OC_max_MiB %.1f' % (max(ou) / 1024, ou[-1] / 1024, max(oc) / 1024))
st = rd('stress.log')
for k in ('Op rate', 'Partition rate', 'Total partitions', 'Total errors', 'Total operation time'):
    m = re.search(r'^%s\s*:\s*(.*)$' % k, st, re.M); print('stress', k, ':', m.group(1).strip() if m else None)
print('oom_count', rd('oom-count.txt').strip(), 'error_warn_lines', len(rd('error-warn.txt').splitlines()))
print('commands_tail:'); print('\n'.join(rd('commands.log').splitlines()[-6:]))
