#!/usr/bin/env python3
"""Tabulates the unit tier's STAGE4 final lines (run.out) per (cap, f) cell and arm, and prints the A-vs-B comparisons used by B2g.
usage: analyze-unit.py <run.out>"""
import re, sys, collections
rows = []
for l in open(sys.argv[1]):
    if l.startswith('STAGE4 final'):
        d = dict(re.findall(r'(\w+)=(\S+)', l)); rows.append(d)
cell = collections.defaultdict(dict)
for d in rows:
    m = re.match(r'([AB])-cap(\d+)-f(\d+)-r(\d+)', d['label']); arm, cap, f, r = m.groups()
    cell[(int(cap), int(f), int(r))][arm] = d
print('cap_MiB f rep | n | A.loaded B.loaded | A.warn B.warn | sumW A / B (cap) | count A/B | A.rows B.rows | memtable A/B (B-A) | liveDelta A/B (B-A) | allocMB A/B')
for k in sorted(cell):
    a, b = cell[k].get('A'), cell[k].get('B')
    if not (a and b): print(k, 'incomplete'); continue
    I = lambda d, x: int(d[x])
    print(f"{k[0]:>3} f{k[1]:<2} r{k[2]} | {I(a,'n')} | {a['loaded']} {b['loaded']} | {a['warn']} {b['warn']} | {a['sumWeights']} / {b['sumWeights']} ({a['cap']}) | {a['count']}/{b['count']} | {a['rowsAfter']} {b['rowsAfter']} | "
          f"{a['memtableAfter']}/{b['memtableAfter']} ({I(b,'memtableAfter')-I(a,'memtableAfter')}) | {a['liveDelta']}/{b['liveDelta']} ({I(b,'liveDelta')-I(a,'liveDelta')}) | {a['allocMB']}/{b['allocMB']}")
print('\npositive control (arm B, f3, rep 1): sumWeights by cap:', {k[0]: int(v['B']['sumWeights']) for k, v in sorted(cell.items()) if k[1] == 3 and k[2] == 1 and 'B' in v})
