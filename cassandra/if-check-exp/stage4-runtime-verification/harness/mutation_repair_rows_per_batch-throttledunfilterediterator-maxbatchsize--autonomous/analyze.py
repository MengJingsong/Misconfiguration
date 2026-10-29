#!/usr/bin/env python3
"""usage: analyze.py <arm-folder> -> readings of one cluster arm of the mutation_repair_rows_per_batch case (B3d/B3g as amended C4).
Files: stdout-B.txt (S4BATCH / S4THROTTLE Byteman lines), samples.txt (class-histogram sampler), gc-B.log (G1 log), system-B.log, repair.txt, count-B.txt."""
import re, sys, os
d = sys.argv[1]
so = open(d + '/stdout-B.txt', errors='replace').read().splitlines()
th = [re.search(r'maxBatchSize=(-?\d+)', l).group(1) for l in so if l.startswith('S4THROTTLE')]
bt = [l for l in so if l.startswith('S4BATCH')]
rows = [int(re.search(r'rows=(\d+)', l).group(1)) for l in bt]
heap = [int(re.search(r'heap=(\d+)', l).group(1)) for l in bt]
data = [int(re.search(r'data=(\d+)', l).group(1)) for l in bt]
print('S4THROTTLE calls:', len(th), 'values:', sorted(set(th)))
print('S4BATCH updates:', len(bt), '| rows: max', max(rows) if rows else '-', 'min', min(rows) if rows else '-', 'total', sum(rows), '| updates with rows == max:', sum(1 for r in rows if r == max(rows)) if rows else '-')
if rows:
    print('  unsharedHeapSize: max', max(heap), 'bytes; per row of the largest update: %.1f' % (max(heap) / max(rows)), ' dataSize max', max(data))
    print('  heap per row over all updates: min %.1f max %.1f' % (min(h / r for h, r in zip(heap, rows)), max(h / r for h, r in zip(heap, rows))))
s = [l for l in open(d + '/samples.txt', errors='replace') if 'total_live_bytes=' in l]
tl = []
for l in s:
    m = re.search(r'total_live_bytes=(\d+)', l)
    if m: tl.append(int(m.group(1)))
print('sampler: %d histograms every ~4 s; live bytes: first %s max %s last %s' % (len(tl), tl[0] if tl else '-', max(tl) if tl else '-', tl[-1] if tl else '-'))
after = []
for l in open(d + '/gc-B.log', errors='replace'):
    m = re.search(r'Pause (?:Young|Mixed|Full)[^\n]*?(\d+)M->(\d+)M\((\d+)M\)', l)
    if m: after.append(int(m.group(2)))
print('G1 pauses:', len(after), ' max heap after pause (MiB):', max(after) if after else '-')
log = open(d + '/system-B.log', errors='replace').read().splitlines()
for pat in ['MutationExceededMaxSizeException', 'java\\.lang\\.OutOfMemoryError', 'Stream failed', 'Repair command .* failed|Repair session .* failed|failed with error', 'Streaming error occurred']:
    c = [l for l in log if re.search(pat, l)]
    print('system.log lines /%s/: %d' % (pat, len(c))); [print('    ', re.sub(r'\s+', ' ', x)[:230]) for x in c[:2]]
rp = open(d + '/repair.txt', errors='replace').read().splitlines()
print('repair.txt tail:', [re.sub(r'\s+', ' ', x)[:160] for x in rp[-3:]])
if os.path.exists(d + '/count-B.txt'):
    print('count-B:', ' '.join(x.strip() for x in open(d + '/count-B.txt') if re.match(r'\s*\d+\s*$', x) or 'rror' in x or 'imeout' in x)[:200])
ta = d + '/tablestats-B-after.txt'
if os.path.exists(ta): print('B after:', ' | '.join(x.strip() for x in open(ta)))
