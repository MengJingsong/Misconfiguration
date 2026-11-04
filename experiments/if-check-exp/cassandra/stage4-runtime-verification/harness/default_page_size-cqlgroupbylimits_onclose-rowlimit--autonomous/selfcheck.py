#!/usr/bin/env python3
"""Self-check (step 4) of default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous: independent re-parse of the raw cluster logs,
not reusing cluster-analyze.py. usage: selfcheck.py <cluster-log-dir>
For every query cell: trace lines inside its window -> reads and rows (K=2 lines per read), max rows/line, the last GC pause lines before the end of
the window for dead cells (evidence for the OutOfMemoryError reading), and the tail of the heap sample."""
import glob, json, os, re, sys, datetime as dt
D = sys.argv[1]
cells = [json.loads(l) for l in open(f'{D}/cells.jsonl')]
for v in ('stock', '500', '200000'):
    tr = [tuple(map(int, m.groups()[:3])) for l in open(f'{D}/{v}/dps.trace') for m in [re.search(r'GB ms=(\d+) rows=(\d+) groups=(\d+)', l)] if m]
    gcl = []
    for fn in sorted(glob.glob(f'{D}/{v}/gc.log*')):
        for l in open(fn, errors='replace'):
            m = re.match(r'^\[([^\]]+)\].*Pause (\w+)[^\n]* (\d+)M->(\d+)M\((\d+)M\) ([\d.]+)ms', l)
            if m:
                ts = re.sub(r'([+-]\d\d)(\d\d)$', r'\1:\2', m[1])
                gcl.append((int(dt.datetime.fromisoformat(ts).timestamp() * 1000), l.strip()))
    for c in [c for c in cells if c.get('variant') == v and c.get('label') in ('groupby-unset', 'plain-count', 'groupby-fetch')]:
        w = [t for t in tr if c['t0'] - 300 <= t[0] <= c['t1'] + 300]
        rows = sum(t[1] for t in w) // 2
        print(f"{v:7s} {c['label']:14s} fetch={c['fetch']} rep={c['rep']} lines={len(w)} reads={len(w)//2} rows={rows} maxrows={max([t[1] for t in w] or [0])} dead={c['dead']} wall={c['wall_ms']}")
        if c['dead']:
            last = [x for x in gcl if c['t0'] - 500 <= x[0] <= c['t1'] + 2000][-3:]
            for x in last:
                print('      GC:', x[1][:150])
