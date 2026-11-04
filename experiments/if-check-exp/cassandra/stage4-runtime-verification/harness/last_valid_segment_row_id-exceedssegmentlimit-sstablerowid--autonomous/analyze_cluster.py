#!/usr/bin/env python3
"""usage: analyze_cluster.py <run dir>   -> ANALYSIS lines: segment count and per-segment rows (segments.txt), peak SegmentBufferSpaceUsedBytes (segbuf.csv), heap used peak (heap.csv),
peak heap occupancy after GC (gc-<label>.log), Global-limit and Flushed-segment line counts (readings.txt), index component bytes."""
import glob, re, sys
d = sys.argv[1]
seg = []
for l in open(d + '/segments.txt'):
    p = [x.strip() for x in l.split('|')]
    if len(p) == 5 and p[1].lstrip('-').isdigit(): seg.append((int(p[1]), int(p[2]), int(p[3]), int(p[4])))
rows = [s[1] for s in seg]
print('ANALYSIS segments=%d rowsMax=%d rowsMin=%d rowsSum=%d spanMax=%d' % (len(seg), max(rows or [0]), min(rows or [0]), sum(rows), max([s[3] - s[2] for s in seg] or [0])))
if len(seg) <= 600: print('ANALYSIS rowsPerSegment=%s' % rows[:12])
sb = [int(l.split(',')[1]) for l in open(d + '/segbuf.csv') if re.match(r'^\d+,\d+', l)]
print('ANALYSIS segbufPeakBytes=%d samples=%d' % (max(sb or [0]), len(sb)))
h = [int(l.split(',')[1]) for l in open(d + '/heap.csv').read().splitlines()[1:] if l.split(',')[1] not in ('-1', '')]
print('ANALYSIS heapUsedSampledPeak_MB=%.0f samples=%d' % (max(h or [0]) / 1024.0, len(h)))
after = []
for f in glob.glob(d + '/gc-*.log'):
    for l in open(f, errors='replace'):
        m = re.search(r'Pause (?:Young|Full|Remark|Cleanup).*? (\d+)M->(\d+)M\((\d+)M\)', l)
        if m: after.append(int(m.group(2)))
print('ANALYSIS heapAfterGcPeak_MB=%d gcPauses=%d' % (max(after or [0]), len(after)))
for l in open(d + '/readings.txt'):
    if l.startswith(('GLOBAL_LIMIT', 'INDEX_', 'RUN_DONE')): print('ANALYSIS ' + l.strip())
tot = sum(int(l.split()[0]) for l in open(d + '/components.txt') if 'SAI' in l); print('ANALYSIS saiComponentBytes=%d' % tot)
