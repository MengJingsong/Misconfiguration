#!/usr/bin/env python3
"""GC-log summary per arm: Full GC count, max/last after-Full-GC occupancy, STW fraction (best 60 s window and
last 120 s before the end of the log). Usage: python3 -I gc_window.py <arm node-logs dir> ..."""
import glob, os, re, sys
from datetime import datetime
for d in sys.argv[1:]:
    files = sorted(glob.glob(d + '/gc.log*'), key=lambda p: (0 if p.endswith('.log') else 1, p))
    lines = []
    for p in files: lines += open(p, errors='replace').read().splitlines()
    ev = []; fulls = []
    for l in lines:
        m = re.match(r'\[([^\]]+)\]\[([\d.]+)s\]', l)
        if not m: continue
        t = float(m.group(2))
        s = re.search(r'Total time for which application threads were stopped: ([\d.]+) seconds', l)
        if s: ev.append((t, float(s.group(1))))
        f = re.search(r'Pause Full \(([^)]*)\) (\d+)M->(\d+)M', l)
        if f: fulls.append((t, f.group(1), int(f.group(2)), int(f.group(3))))
    ev.sort()
    end = ev[-1][0] if ev else 0
    best = 0; bt = 0
    for i, (t, _) in enumerate(ev):
        tot = sum(max(0.0, min(u, t) - max(u - dur, t - 60)) for (u, dur) in ev if u > t - 60 and u - dur < t)  # STW overlap with (t-60, t]
        if tot / 60 > best: best, bt = tot / 60, t
    last120 = sum(max(0.0, min(u, end) - max(u - dur, end - 120)) for (u, dur) in ev if u > end - 120) / 120
    evac = [x for x in fulls if 'Diagnostic' not in x[1]]
    first95 = next((x[0] for x in evac if x[3] >= 973), None)
    print('%s: fullGC(non-diag)=%d max_after=%s first_after>=973M at %ss; log end %.0fs; best60s STW=%.0f%% (ending %.0fs); last120s STW=%.0f%%'
          % (os.path.abspath(d).split("/")[-2], len(evac), max((x[3] for x in evac), default='-'), first95, end, best * 100, bt, last120 * 100))
