#!/usr/bin/env python3
"""R13 stage 2 (added 2026-11-20 12:45 ET, analysis only): stw.py <run dir> <end ISO time, e.g. 2026-11-20T10:42:27.000-0700>
STW share of the GC log (each pause line once, clipped to the window) over the 60 / 120 / 180 s before <end>; for the
service-loss criterion (>= 90 % STW over >= 60 s) when a run ends at the hold end without an OOM."""
import datetime, glob, os, re, sys
R, end = sys.argv[1], datetime.datetime.strptime(sys.argv[2], '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
seen = {}
for f in glob.glob(os.path.join(R, 'gc.log*')):
    for l in open(f, errors='replace'):
        m = re.match(r'\[(\S+?)\]\[(\d+\.\d+)s\].*GC\((\d+)\) (Pause .*?) (\d+)M->(\d+)M\(\d+M\) (\d+\.\d+)ms', l)
        if m:
            seen[(m.group(3), m.group(4))] = (datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp(),
                                             float(m.group(7)) / 1000)
for w in (60, 120, 180):
    s = sum(max(0.0, min(t, end) - max(t - d, end - w)) for t, d in seen.values())
    print('%s: %d s window before %s: STW %.1f s = %.0f%%' % (os.path.basename(R.rstrip('/')), w, sys.argv[2], s, 100 * s / w))
