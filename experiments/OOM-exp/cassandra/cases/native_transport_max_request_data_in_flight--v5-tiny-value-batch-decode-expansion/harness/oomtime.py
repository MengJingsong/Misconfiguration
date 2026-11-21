#!/usr/bin/env python3
"""R13 stage 2 (added 2026-11-20, analysis only): oomtime.py <run dir>...: per run, the OOM time relative to the last
connection established (the 'HeapDumper' safepoint in the GC log, or the last GC line when no dump was taken), the first
Full GC and the span of Full GCs, and the heap after the Full GCs in the last 60 s before the endpoint (each GC id once)."""
import datetime, glob, os, re, sys

for R in sys.argv[1:]:
    est = []
    for f in glob.glob(os.path.join(R, 'client-p*.txt')):
        for l in open(f):
            if l.startswith('# established'): est.append(int(l.split(' at ')[1]))
    t0 = max(est) / 1000 if est else None
    seen = {}; hd = None; hd_end = None; last = None
    so = open(os.path.join(R, 'stdout.txt'), errors='replace').read() if os.path.exists(os.path.join(R, 'stdout.txt')) else ''
    dm = re.search(r'Heap dump file created \[\d+ bytes in (\d+\.\d+) secs\]', so)
    for f in sorted(glob.glob(os.path.join(R, 'gc.log*'))):
        for l in open(f, errors='replace'):
            m = re.match(r'\[(\S+?)\]\[(\d+\.\d+)s\]', l)
            if not m: continue
            ts = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%S.%f%z').timestamp()
            last = ts if last is None or ts > last else last
            if 'Entering safepoint region: HeapDumper' in l and hd is None: hd = ts
            elif hd is not None and hd_end is None and 'Leaving safepoint region' in l and ts >= hd: hd_end = ts
            g = re.search(r'GC\((\d+)\) (Pause Full[^\n]*?) (\d+)M->(\d+)M\(\d+M\) (\d+\.\d+)ms', l)
            if g: seen[int(g.group(1))] = (ts, int(g.group(4)), float(g.group(5)))
    full = sorted(seen.values())
    oom = (hd_end - float(dm.group(1))) if (hd_end and dm) else hd
    end = oom or last
    rel = lambda t: '%+.1f' % (t - t0) if (t0 and t) else '?'
    w = [a for t, a, ms in full if end and end - 60 <= t <= end]
    print('%s: OOM=%s s (HeapDumper enter %s s)  first Full GC=%s s  Full GCs=%d  after-Full in last 60 s before end: n=%d min=%s max=%s MiB' % (
        os.path.basename(R.rstrip('/')), rel(oom) if oom else 'none(last GC line %s)' % rel(last), rel(hd) if hd else '-', rel(full[0][0]) if full else '-',
        len(full), len(w), min(w) if w else '-', max(w) if w else '-'))
