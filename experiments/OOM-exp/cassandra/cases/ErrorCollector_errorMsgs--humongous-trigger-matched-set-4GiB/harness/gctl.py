#!/usr/bin/env python3
"""U6: GC timeline from gc.log* in a run dir: one line per GC pause (dedup by GC id), wall time, uptime, type, before->after MiB,
pause ms; then per-30-s windows: STW share and max after-GC. Usage: gctl.py <run dir> [--all]"""
import glob, os, re, sys
R = sys.argv[1]; ev = {}
pat = re.compile(r'^\[([^\]]+)\]\[(\d+\.\d+)s\]\[\d+\]\[\d+\]\[info\s*\] GC\((\d+)\) (Pause [^\n]*?) (\d+)M->(\d+)M\(\d+M\) (\d+\.\d+)ms', re.M)
for f in glob.glob(os.path.join(R, 'gc.log*')):
    for m in pat.finditer(open(f, errors='replace').read()):
        ev[int(m.group(3))] = (m.group(1)[11:23], float(m.group(2)), m.group(4).replace(' ', '_'), int(m.group(5)), int(m.group(6)), float(m.group(7)))
ev = [ev[k] for k in sorted(ev)]
if '--all' in sys.argv:
    for e in ev: print(*e)
if not ev: sys.exit()
t0 = ev[0][1]; w = {}
for e in ev:
    k = int((e[1] - t0) // 30); a = w.setdefault(k, [0.0, 0, 0, e[0]]); a[0] += e[5]; a[1] = max(a[1], e[4]); a[2] += 'Full' in e[2]
for k in sorted(w):
    a = w[k]; print('win %s +%4ds stw %3.0f%% maxafter %5d MiB full %d' % (a[3], k * 30, a[0] / 300, a[1], a[2]))
