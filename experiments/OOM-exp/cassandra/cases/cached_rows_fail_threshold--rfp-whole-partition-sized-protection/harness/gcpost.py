#!/usr/bin/env python3
# R24 (2026-11-24): U from the shipped GC log (design §2.6 b): heap after every Pause Full, and the max heap after any young/mixed
# pause; G1 'Pause ... A->B(C)' lines.   gcpost.py <dir-with-gc.log*>
import glob, re, sys
pat = re.compile(r'\]\[([0-9.]+)s\].*(Pause [A-Za-z0-9 ()]+?) ([0-9]+)M->([0-9]+)M\(([0-9]+)M\) ([0-9.]+)ms')
full = []; yg = []
for f in sorted(glob.glob(sys.argv[1] + '/gc.log*')):
    for line in open(f, errors='replace'):
        m = pat.search(line)
        if not m: continue
        t, kind, a, b = float(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        (full if 'Full' in kind else yg).append((t, b, kind.strip()))
print(f"full_gcs={len(full)} after-full MiB: {' '.join(f'{b}@{t:.0f}s' for t, b, _ in full[-12:])}")
print(f"max after-full={max((b for _, b, _ in full), default=-1)} MiB; max after young/mixed={max((b for _, b, _ in yg), default=-1)} MiB; young/mixed pauses={len(yg)}")
