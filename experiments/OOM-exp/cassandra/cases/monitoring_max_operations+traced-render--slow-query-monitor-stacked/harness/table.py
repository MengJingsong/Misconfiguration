#!/usr/bin/env python3
"""table.py <runs dir> <run-id>...: one markdown row per run from its summary.txt / driver.txt / threads.txt."""
import os, re, sys
from collections import Counter
R = sys.argv[1]
print('| Run | Endpoint | t after full N (s) | ok | median lat (ms) | errors | max R | ST in popOperations / samples | U_h after GC median / max (regions) | Full GCs | slow drains logged (queued, dropped) | failed drains (queued) |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|')
for rid in sys.argv[2:]:
    d = os.path.join(R, rid)
    try: s = open(os.path.join(d, 'summary.txt'), errors='replace').read()
    except OSError: continue
    ep = re.search(r'endpoint: (\S+)(.*)', s); ep = ('heap OOM' if 'OutOfMemoryError' in ep.group(2) else ep.group(1)) + (' (after hold end)' if ep.group(1) == 'hold' and 'OutOfMemoryError' in ep.group(2) else '')
    t = re.search(r'last completion line at \d+ ms \(\+([\d.]+) s\)', s)
    ok = re.search(r'ok completions after it: (\d+)', s)
    lat = re.findall(r'step N=\d+: ok \d+, median latency (\S+) ms', s)
    er = re.search(r'client max established \d+, completed \d+, errors (\d+)', s)
    mr = re.search(r'max R\(traceQuery\) (\d+)', s)
    st = re.search(r'ST series: (.*)', s); stc = '-'
    if st:
        v = st.group(1).split(); stc = '%d/%d' % (sum(1 for x in v if x.startswith('pop')), len(v))
    h = re.search(r'humongous after GC: max (\d+) regions \(\d+ MiB\), median (\d+)', s)
    fg = re.search(r'Pause Full count (\d+)', s)
    sd = [(int(a), int(b)) for a, b in re.findall(r'were_slow +n=\d+ interval_ms=\d+ names=\d+ queued=(\d+) dropped=(\d+)', s)]
    fd = [int(a) for a in re.findall(r'timed_out +n=\d+ interval_ms=\d+ names=\d+ queued=(\d+)', s)]
    print('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (rid, ep, t.group(1) if t else '-', ok.group(1) if ok else '-',
          lat[-1] if lat else '-', er.group(1) if er else '-', mr.group(1) if mr else '-', stc,
          '%s / %s' % (h.group(2), h.group(1)) if h else '-', fg.group(1) if fg else '-',
          (str(len(sd)) + ' (' + ', '.join('%d, %d' % x for x in sd) + ')') if sd else '0', (str(len(fd)) + ' (' + ', '.join(map(str, fd)) + ')') if fd else '0'))
