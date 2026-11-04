#!/usr/bin/env python3
"""Prints the cluster cells of one case (or all) in a fixed pseudo-random order: `tag variant workload heap_MiB`.  usage: cells.py [1|2|3|4|all]
Order: random.Random(20261028 + case).shuffle within a case (variant order randomized, as the case files ask)."""
import random, sys
CELLS = {
 1: [('c1-%s-r%d' % (v, r), v, 'WA', 512) for v in ('v10m', 'v1', 'v2p40') for r in (1, 2, 3)] + [('c1-ctl128', 'v10m', 'WA', 128), ('c1-ctl1024', 'v10m', 'WA', 1024)],
 2: [('c2-hot', 'v10m', 'WB', 512), ('c2-cold', 'v10m', 'WC', 512), ('c2-hot128', 'v10m', 'WB', 128), ('c2-cold128', 'v10m', 'WC', 128),
     ('c2-hot-v1m', 'v1m', 'WB', 512), ('c2-hot-v100m', 'v100m', 'WB', 512)],
 3: [('c3-%s-%s-r%d' % (w, v, r), v, w, 512) for w in ('WD', 'WE') for v in ('v1m', 'v10m', 'v1g') for r in (1, 2)] + [('c3-ctl128', 'v10m', 'WD', 128), ('c3-single', 'v1m', 'W1', 512)],
 4: [('c4-%s-%s' % (w, v), v, w, 512) for w in ('WF', 'WG') for v in ('v10m', 'v1g', 'v1024')] + [('c4-ctl128', 'v10m', 'WF', 128), ('c4-ctl1024', 'v10m', 'WF', 1024)],
}
which = sys.argv[1] if len(sys.argv) > 1 else 'all'
for c in ([1, 2, 3, 4] if which == 'all' else [int(which)]):
    cells = list(CELLS[c]); random.Random(20261028 + c).shuffle(cells)
    for t in cells: print(*t)
