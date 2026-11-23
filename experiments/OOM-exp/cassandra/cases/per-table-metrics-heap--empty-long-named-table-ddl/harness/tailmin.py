#!/usr/bin/env python3
"""U14 (2026-11-23): per-minute table of the last <minutes> of a lifetime's sampler.csv, the format of logs/<label>-tail-per-minute.txt.
usage: tailmin.py <logs dir>/<label> [<minutes>=15]
gc% = (young+old collection time delta)/wall over the minute; old_n = old-gen collections that minute; heap/old_coll MiB at the
minute end; creates = ok CREATEs that minute (client.csv); last_i = last ok table index by the minute end. Times America/New_York."""
import os, sys, time
d = sys.argv[1]; mins = int(sys.argv[2]) if len(sys.argv) > 2 else 15
os.environ['TZ'] = 'America/New_York'; time.tzset()
label = os.path.basename(d.rstrip('/'))
smp = []
for l in open(d + '/sampler.csv'):
    p = l.strip().split(',')
    if p[0].isdigit() and len(p) >= 10 and all(x.lstrip('-').isdigit() for x in p[:9]):
        smp.append(p)
ok = []
for l in open(d + '/client.csv'):
    p = l.split(',', 5)
    if p[0].isdigit() and p[2] == 'create' and p[4] == 'ok':
        ok.append((int(p[0]), int(p[1])))
bym = {}
for p in smp:
    bym.setdefault(int(p[0]) // 60000, []).append(p)
keys = sorted(bym)[-mins:]
print(f'# {label}: last {mins} min of sampler.csv, per minute (EST). gc% = (young+old collection time delta)/wall; heap/old_coll MiB at '
      'the minute end; creates = ok CREATEs that minute; last_i = last ok table index')
print('minute  gc%   old_n  heap_MiB  old_coll_MiB  memtables_MiB  mbeans    creates  last_i')
prev = None
allk = sorted(bym)
for k in keys:
    rows = bym[k]
    i = allk.index(k)
    first = bym[allk[i - 1]][-1] if i > 0 else rows[0]
    last = rows[-1]
    wall = int(last[0]) - int(first[0])
    gc = (int(last[5]) + int(last[7])) - (int(first[5]) + int(first[7]))
    oldn = int(last[6]) - int(first[6])
    t0, t1 = k * 60000, (k + 1) * 60000
    cr = sum(1 for ms, _ in ok if t0 <= ms < t1)
    li = max([i_ for ms, i_ in ok if ms < t1], default=0)
    mt = float(last[9]) / 1048576 if last[9].lstrip('-').replace('.', '').isdigit() else float('nan')
    print(f"{time.strftime('%H:%M', time.localtime(k * 60))}  {round(100 * gc / wall) if wall else 0:4d}  {oldn:6d}  {int(last[1]) // 1048576:8d}  "
          f"{int(last[3]) // 1048576:12d}  {mt:13.1f}  {int(last[8]):8d}  {cr:7d}  {li:6d}")
