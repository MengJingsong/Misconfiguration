#!/usr/bin/env python3
"""U13: u13.t flushes from system.log. usage: flushes.py <system.log> count|table
Enqueue lines: 'Enqueuing flush of u13.t, Reason: R, Usage: X (P%) on-heap, ...'; writing lines: 'Writing Memtable-t@...(S serialized
bytes, N ops, ...)'; completion lines: 'Completed flushing .../u13/t-.../...-Data.db (SIZE) for commitlog position ...'.
count: number of completed u13.t flushes, capped at the number of enqueues with on-heap usage >= 30 % (0.9 x predicted 1/3).
table: one line per event with time, thread, and parsed numbers."""
import re, sys

path, mode = sys.argv[1], sys.argv[2]
enq, wr, done = [], [], []
pat_t = re.compile(r'^(\w+)\s+\[([^\]]+)\]\s+(\S+ \S+)')
with open(path, errors='replace') as f:
    for line in f:
        if 'Enqueuing flush of u13.t,' in line:
            m = re.search(r'Usage: ([0-9.]+\w+) \((\d+)%\) on-heap', line)
            enq.append((line[:120].strip(), m.group(1) if m else '?', int(m.group(2)) if m else -1))
        elif 'Writing Memtable-t@' in line:
            m = re.search(r'\(([0-9.]+\w+) serialized bytes, (\d+) ops', line)
            wr.append((line[:100].strip(), m.group(1) if m else '?', int(m.group(2)) if m else -1))
        elif 'Completed flushing' in line and '/u13/t-' in line:
            m = re.search(r'\(([0-9.]+\w+)\) for commitlog', line)
            done.append((line[:100].strip(), m.group(1) if m else '?'))
big = sum(1 for e in enq if e[2] >= 30)
if mode == 'count':
    print(min(len(done), big))
else:
    print(f'enqueues={len(enq)} (>=30%: {big}) writing={len(wr)} completed={len(done)}')
    for e in enq:
        print('ENQ ', e[1], f'{e[2]}%', '|', e[0])
    for w in wr:
        print('WRITE', w[1], w[2], 'ops |', w[0])
    for d in done:
        print('DONE', d[1], '|', d[0])
