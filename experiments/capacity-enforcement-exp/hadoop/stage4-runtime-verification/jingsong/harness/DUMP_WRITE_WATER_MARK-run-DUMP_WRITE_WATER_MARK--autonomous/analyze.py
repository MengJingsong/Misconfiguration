#!/usr/bin/env python3
"""Readings from one cluster run's gateway log (B3d): counter at PAUSE (last counter value before the hole-filling
write at offset 0), max counter, number of times the counter equals the mark, stream-cleanup times vs DONE.
Usage: analyze.py <obs/run dir> <mark bytes>"""
import gzip, re, sys, os
d, mark = sys.argv[1], int(sys.argv[2])
lines = gzip.open(os.path.join(d, 'nfs3.log.gz'), 'rt', errors='replace').read().splitlines()
upd = re.compile(r'Update nonSequentialWriteInMemory by (-?\d+) new value: (\d+)')
vals, first_zero_req, cleanup_ts, create_ts, ask = [], None, [], [], 0
per_file_max = 0
for i, l in enumerate(lines):
    m = upd.search(l)
    if m:
        vals.append((i, int(m.group(1)), int(m.group(2)), l[:23]))
    if first_zero_req is None and 'requested offset=0 ' in l:
        first_zero_req = i
    if re.search(r'There are \d+ pending writes', l):
        cleanup_ts.append(l[:23] + ' ' + l.split('There are')[1].strip())
    if 'Create dump file' in l:
        create_ts.append(l[:23])
inc = [v for v in vals if v[1] > 0]
print('updates', len(vals), 'increments', len(inc), 'decrements', len(vals) - len(inc))
print('max counter', max(v[2] for v in vals) if vals else None)
print('increments reaching mark', sum(1 for v in inc if v[2] == mark))
print('increments above mark', sum(1 for v in inc if v[2] > mark))
print('increment sizes', sorted(set(v[1] for v in inc)))
if first_zero_req is not None:
    before = [v for v in vals if v[0] < first_zero_req]
    print('first offset-0 request at log line', first_zero_req + 1, lines[first_zero_req][:23])
    print('counter at PAUSE (last value before it)', before[-1][2] if before else 0)
print('dump files created', len(create_ts), create_ts[:3], '...' if len(create_ts) > 3 else '')
print('stream cleanups', cleanup_ts)
print('last counter value', vals[-1][2] if vals else None, vals[-1][3] if vals else '')
