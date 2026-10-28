#!/usr/bin/env python3
"""Tabulates the cluster tier's per-start summary.txt files. usage: analyze-cluster.py <dir with A-cap1-r1/ B-cap1-r1/ ...>"""
import os, re, sys
d = sys.argv[1]
print('tag | preload(N,ms) | WARN | count evicted memtableHeap | live_bytes | Prepared instances (shallow) | rows')
res = {}
for tag in sorted(os.listdir(d)):
    f = os.path.join(d, tag, 'summary.txt')
    if tag == 'seed' or not os.path.exists(f): continue
    t = open(f).read()
    pre = re.search(r"PRELOAD lines=\[\('(\d+)', '(\d+)'\)\]; filling-up warnings=(\d+)", t)
    c = re.search(r'COUNTERS count=(\d+) evicted=(\d+) memtable_heap=(\d+)', t)
    h = re.search(r'HISTO after-preload live_bytes=(\d+) live_objects=(\d+) prepared_instances=(\d+) prepared_shallow=(\d+)', t)
    r = re.search(r'ROWS system.prepared_statements: (\d+)', t)
    if not (pre and c and h and r): print(tag, 'INCOMPLETE'); continue
    res[tag] = dict(loaded=int(pre.group(1)), ms=int(pre.group(2)), warn=int(pre.group(3)), count=int(c.group(1)), ev=int(c.group(2)), mt=int(c.group(3)),
                    live=int(h.group(1)), prep=int(h.group(3)), shallow=int(h.group(4)), rows=int(r.group(1)))
    x = res[tag]
    print(f"{tag} | ({x['loaded']},{x['ms']}) | {x['warn']} | {x['count']} {x['ev']} {x['mt']} | {x['live']} | {x['prep']} ({x['shallow']}) | {x['rows']}")
print()
for cap in (1, 4, 10):
    for r in (1, 2):
        a, b = res.get(f'A-cap{cap}-r{r}'), res.get(f'B-cap{cap}-r{r}')
        if a and b:
            print(f"cap {cap} MiB rep {r}: loaded A={a['loaded']} B={b['loaded']}; Prepared instances A={a['prep']} B={b['prep']}; live B-A={b['live']-a['live']} B ({(b['live']-a['live'])/(cap*1048576):.2f} caps); memtable B-A={b['mt']-a['mt']}; rows A={a['rows']} B={b['rows']}")
