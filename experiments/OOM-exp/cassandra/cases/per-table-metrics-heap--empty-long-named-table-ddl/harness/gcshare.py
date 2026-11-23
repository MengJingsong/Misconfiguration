#!/usr/bin/env python3
"""U14 (2026-11-23): stop-the-world share from the shipped gc.log* (all rotated files of one lifetime), the protocol's
service-loss criterion (>= 90 % STW over >= 60 s). usage: gcshare.py <logs dir>/<label> [<minutes>=20]
Prints the time span the logs cover, per-minute STW % (pause ms per wall minute, America/New_York) for the last <minutes>, and the
longest stretch of consecutive whole minutes at >= 90 %. Pauses: lines '... Pause <kind> ... <ms>ms' (G1 Young, Full, Remark, Cleanup)."""
import glob, os, re, sys, time, datetime
d = sys.argv[1]; mins = int(sys.argv[2]) if len(sys.argv) > 2 else 20
os.environ['TZ'] = 'America/New_York'; time.tzset()
pat = re.compile(r'^\[(\S+?)\]\[[\d.]+s\].*GC\(\d+\) Pause (\S+).* ([\d.]+)ms$')
per = {}; seen = set(); first = last = None
for f in glob.glob(d + '/gc.log*'):
    for l in open(f, errors='replace'):
        m = pat.match(l.rstrip())
        if not m or l in seen:
            continue
        seen.add(l)
        t = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
        first = t if first is None or t < first else first; last = t if last is None or t > last else last
        k = int(t // 60); per[k] = per.get(k, 0.0) + float(m.group(3))
if not per:
    sys.exit('no pause lines')
fmt = lambda t: time.strftime('%H:%M:%S', time.localtime(t))
print(f'# {os.path.basename(d.rstrip("/"))}: STW pauses from gc.log* (covers {fmt(first)}-{fmt(last)} EST); pct = pause ms / 60,000 per minute')
ks = list(range(min(per), max(per) + 1))
run = best = 0; best_end = None
for k in ks[1:-1]:   # whole minutes only
    if per.get(k, 0) >= 54000:
        run += 1
        if run > best:
            best, best_end = run, k
    else:
        run = 0
if best:
    print(f'longest run of whole minutes >= 90 % STW: {best} min, {fmt((best_end - best + 1) * 60)}-{fmt((best_end + 1) * 60)}')
else:
    print('no whole minute >= 90 % STW')
print('minute  stw%')
for k in ks[-mins:]:
    print(f"{time.strftime('%H:%M', time.localtime(k * 60))}  {round(per.get(k, 0) / 600):4d}")
