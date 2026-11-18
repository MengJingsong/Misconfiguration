#!/usr/bin/env python3
"""C8: for each run dir, print the build start (system.log 'Starting a compaction index build'), the last gauge row
(K_D1, heap used, K_D2, key cache) and the full-GC count/STW in the last 60 s of the run. usage: oomtail.py <rundir>..."""
import glob, re, sys
from datetime import datetime, timezone

for R in sys.argv[1:]:
    ta = int(open(R + '/t_arm.txt').read())
    rows = [l.strip().split(',') for l in open(R + '/gauges.csv') if l[0].isdigit()]
    rows = [[int(x) for x in r] for r in rows if len(r) >= 11]
    sl = ''.join(open(f, errors='replace').read() for f in sorted(glob.glob(R + '/system.log*')))
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d+) V1OnDiskFormat.java:\d+ - .*Starting a compaction index build', sl)
    bs = None
    if m:
        t = datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc).timestamp() * 1000 + int(m.group(2))
        bs = (t - ta) / 1000
    last = rows[-1]
    kc = f' KC={last[11] >> 20}MiB/{last[12]}e' if len(last) > 12 else ''
    t_last = (last[0] - ta) / 1000
    print(f'{R.split("/")[-1]}: build_start=arm+{bs}s last_sample=arm+{t_last:.0f}s (build+{t_last - bs if bs else 0:.0f}s) '
          f'K1={last[1] >> 20}MiB heap={last[4] >> 20}MiB K2={last[6] >> 20}MiB blocked={last[7]} oldGC={last[10]}{kc}')
