#!/usr/bin/env python3
"""usage: unit-summary.py <harness.out>      (native_transport_max_message_size case, unit tier)
Tabulates the STAGE4 reading lines and prints the 9a-relevant figures: for the 8 MiB request (req8m) the kept buffer bytes
at each limit, and for each limit the above/at/below boundary (toobig, buffers, discarded, response). Prints readings only;
the row is chosen in the results file (R2 tolerances: about 8 MiB = 6-10 MiB, about one frame <= 1 MiB)."""
import re, sys

MiB = 1 << 20
rows = []
for l in open(sys.argv[1]):
    if l.startswith('STAGE4 reading '):
        rows.append(dict(re.findall(r'(\w+)=(\S*)', l)))
print(f'readings: {len(rows)}')
print('step                 limit     body      frames sent lm toobig buffers buffer_bytes  disc  resp')
for r in rows:
    print(f"{r['step']:<20} {int(r['limit']):>9} {int(r['body']):>9} {r['frames']:>6} {r['sent_frames']:>4} {r['lm']:>2} {r['toobig']:>6} "
          f"{r['buffers']:>7} {int(r['buffer_bytes']):>12} {r['discarded_delta']:>5}  op={r['resp_opcode']} code={r['resp_code']} {r['resp_msg'][:90]}")
for r in rows:
    if r['step'].endswith('req8m'):
        b = int(r['buffer_bytes'])
        band = 'about 8 MiB (6-10 MiB)' if 6 * MiB <= b <= 10 * MiB else ('about one frame (<= 1 MiB)' if b <= MiB else 'neither band')
        print(f"KEPT 8 MiB request at limit {int(r['limit']) // MiB} MiB: {b} B = {b / MiB:.3f} MiB -> {band}")
