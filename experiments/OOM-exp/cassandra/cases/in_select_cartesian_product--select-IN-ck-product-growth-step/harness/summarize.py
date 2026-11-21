#!/usr/bin/env python3
"""U5: one markdown row per lifetime from logs/<label>/ (run.meta, client.jsonl, samples.csv, gcwin.txt, outcome).
   summarize.py <logs dir> <label> ...
Columns: label | arm | heap (-Xmx / MaxDirect) | cond | k1 x k2 = N | K body bytes | client result | latency s |
         JMX heap max / old max / old post-GC max (MiB) | full GCs, max STW in 60 s, longest >= 90 % window | outcome
"""
import json, os, re, sys

d = sys.argv[1]
for L in sys.argv[2:]:
    p = os.path.join(d, L)
    meta = open(os.path.join(p, 'run.meta')).read() if os.path.exists(os.path.join(p, 'run.meta')) else ''
    g = lambda k: (re.search(k + r'=(\S+)', meta) or [None, '?'])[1]
    xmx = (re.search(r'-Xmx(\S+)', meta) or [None, '?'])[1]; mdm = (re.search(r'MaxDirectMemorySize=(\S+)', meta) or [None, '?'])[1]
    sent = res = None
    try:
        for l in open(os.path.join(p, 'client.jsonl')):
            e = json.loads(l)
            if e['ev'] == 'sent': sent = e
            elif e['ev'] != 'prepared': res = e
    except FileNotFoundError:
        pass
    if res is None: rtxt, lat = '-', '-'
    elif res['ev'] == 'result': rtxt, lat = '%s row' % res['rows'], res['latency_s']
    elif res['ev'] == 'error': rtxt, lat = '%s %s' % (res['code'], res['msg'][:60]), res['latency_s']
    else: rtxt, lat = res['ev'], res.get('latency_s', '-')
    mx = mo = mp = 0
    try:
        for l in open(os.path.join(p, 'samples.csv')):
            q = l.split(',')
            if len(q) > 3 and q[1].isdigit():
                mx = max(mx, int(q[1])); mo = max(mo, int(q[2])); mp = max(mp, int(q[3]))
    except FileNotFoundError:
        pass
    gw = open(os.path.join(p, 'gcwin.txt')).read().strip() if os.path.exists(os.path.join(p, 'gcwin.txt')) else ''
    fg = (re.search(r'full_gcs=(\d+)', gw) or [None, '?'])[1]; m60 = (re.search(r'max60=(\d+%)', gw) or [None, '?'])[1]
    lw = (re.search(r'longest>=90%win=(\d+s)', gw) or [None, '?'])[1]
    out = open(os.path.join(p, 'outcome')).read().split(' client=')[0].strip() if os.path.exists(os.path.join(p, 'outcome')) else '?'
    print(f"| `{L}` | {g('arm')} | {xmx} / {mdm} | {g('cond')} | {g('k1')} × {g('k2')} = {int(g('N')):,} | "
          f"{sent['body_bytes'] if sent else '-':,} | {rtxt} | {lat} | {mx/2**20:.0f} / {mo/2**20:.0f} / {mp/2**20:.0f} | "
          f"{fg}, {m60}, {lw} | {out} |" if g('N').isdigit() and sent else f"| `{L}` | {g('arm')} | {xmx} / {mdm} | - | - | - | {rtxt} | {lat} | - | {fg}, {m60}, {lw} | {out} |")
