#!/usr/bin/env python3
"""U6: service-loss criterion from gc.log* in a run dir, restricted to [client start, client end] from driver.txt.
Slides a 60 s window (end at each GC end); prints the max STW share, the first window end with >= 90 %, and the total
time inside the client interval covered by windows with >= 90 %. Usage: stw.py <run dir>"""
import glob, os, re, sys, datetime as dt
R = sys.argv[1]
drv = open(os.path.join(R, 'driver.txt')).read()
def ts(pat):
    m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)-0700 ' + pat, drv)
    return dt.datetime.fromisoformat(m.group(1)).timestamp() if m else None
t0 = ts('baseline done'); t1 = ts('client ended') or ts('daemon gone')
pat = re.compile(r'^\[(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)-0700\]\[[\d.]+s\]\[\d+\]\[\d+\]\[info\s*\] GC\((\d+)\) Pause [^\n]*? \d+M->\d+M\(\d+M\) (\d+\.\d+)ms', re.M)
ev = {}
for f in glob.glob(os.path.join(R, 'gc.log*')):
    for m in pat.finditer(open(f, errors='replace').read()):
        ev[int(m.group(2))] = (dt.datetime.fromisoformat(m.group(1)).timestamp(), float(m.group(3)) / 1000)
ev = sorted(ev.values())   # (start, dur)
def share(end):
    s = 0.0
    for st, d in ev:
        a, b = max(st, end - 60), min(st + d, end)
        if b > a: s += b - a
    return s / 60
pts = [st + d for st, d in ev if t0 + 60 <= st + d <= t1]
best = max(((share(e), e) for e in pts), default=(0, None))
hi = [e for e in pts if share(e) >= 0.9]
print('client interval %.0f s; max 60-s STW share %.0f%% (window end +%.0f s); first >=90%% window end at +%s s; '
      'windows >=90%%: %d of %d GC ends; span first..last >=90%%: %s s' % (
      t1 - t0, 100 * best[0], (best[1] or t0) - t0, '%.0f' % (hi[0] - t0) if hi else '-', len(hi), len(pts),
      '%.0f' % (hi[-1] - hi[0] + 60) if hi else '-'))
