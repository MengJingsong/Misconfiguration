#!/usr/bin/env python3
"""o125 supplementary cluster summary (NOT the verdict reading; B3e step 10 / analyze.py is).
Per run: mean pendingBytes and netPoolUsed in the 10 s before STOP, absolute max netPoolUsed and
directUsed in [STOP+5 s, STOP+20 s], the most negative netPoolUsed in the whole series, and the
max netPoolUsed over the whole series. Usage: supplement.py <dir with one sub-folder per run>"""
import csv, glob, os, sys
MiB = 1 << 20
print('run,pend_pre_mean_MiB,net_pre_mean_KiB,net_win_max_abs_KiB,net_series_max_KiB,net_series_min_KiB,dir_pre_MiB,dir_win_max_MiB,first_neg_net_s_after_stop,drops_first_s_after_stop')
for d in sorted(glob.glob(sys.argv[1] + '/*/')):
    R = os.path.basename(d.rstrip('/'))
    stop = int(open(d + 'stop.ts').read())
    S = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(open(d + 'samples.csv'))]
    pre = [r for r in S if stop - 10000 <= r['ms'] < stop]
    win = [r for r in S if stop + 5000 <= r['ms'] <= stop + 20000]
    neg = [r for r in S if r['netPoolUsed'] < 0]
    drp = [r for r in S if r['overloadDrops'] > 0]
    m = lambda xs, k: sum(r[k] for r in xs) / max(1, len(xs))
    print(R, '%.1f' % (m(pre, 'pendingBytes') / MiB), '%.0f' % (m(pre, 'netPoolUsed') / 1024),
          '%.0f' % (max(r['netPoolUsed'] for r in win) / 1024), '%.0f' % (max(r['netPoolUsed'] for r in S) / 1024),
          '%.0f' % (min(r['netPoolUsed'] for r in S) / 1024), '%.2f' % (m(pre, 'directUsed') / MiB),
          '%.2f' % (max(r['directUsed'] for r in win) / MiB),
          '%.1f' % ((neg[0]['ms'] - stop) / 1000) if neg else 'none',
          '%.1f' % ((drp[0]['ms'] - stop) / 1000) if drp else 'none', sep=',')
