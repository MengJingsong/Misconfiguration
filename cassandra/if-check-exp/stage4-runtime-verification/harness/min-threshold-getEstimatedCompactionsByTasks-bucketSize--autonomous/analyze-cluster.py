#!/usr/bin/env python3
"""EXPECTED lines for the cluster tier (B3f predictions P1-P3, controls C1-C3). usage: analyze-cluster.py summary.txt"""
import csv, json, os, sys
arms, bases = {}, {}
for l in open(sys.argv[1]):
    if l.startswith('ARM '):
        a = json.loads(l[4:]); arms[a['name']] = a
d = os.path.dirname(os.path.abspath(sys.argv[1]))
def ex(desc, ok):
    print(f'EXPECTED: {desc} — {"yes" if ok else "NO"}')
est = [a for a in arms.values() if a['kind'] == 'est']
def by(mn): return [a for a in est if a['min'] == mn]
for mn, want in ((2, 1), (4, 1), (16, 0)):
    g = [(a['name'], a['gauge_max'], a['base']['gauge']) for a in by(mn)]
    ex(f'P1 min={mn}: PendingCompactions max after enable = {want} in every repetition {g}', len(g) > 0 and all(x[1] == want for x in g))
ex('P1b min=16: no compaction ran and 10 sstables remain', all(a['compacted'] == 0 and a['after']['sstables'] == 10 for a in by(16)) and bool(by(16)))
tot = [a['base']['total'] for a in est]; dus = [a['base']['du'] for a in est]; liv = [a['base']['live'] for a in est]
if est:
    ex(f'P2 baseline Space used (total) within 2% across all min and reps ({min(tot)/1e6:.1f}-{max(tot)/1e6:.1f} MB), du ({min(dus)/1e6:.1f}-{max(dus)/1e6:.1f} MB)', max(tot) <= 1.02 * min(tot) and max(dus) <= 1.02 * min(dus))
    ex(f'P2b baseline total ~ 200 MiB (flushed data) ({sum(tot)/len(tot)/1048576:.0f} MiB mean)', 150 * 1048576 < sum(tot) / len(tot) < 260 * 1048576)
    for k, lab in (('heap', 'live heap (class histogram total)'), ('rss', 'RssAnon')):
        mean = {mn: sum(a['base'][k] for a in by(mn)) / len(by(mn)) for mn in (2, 4, 16) if by(mn)}
        sp = (max(mean.values()) - min(mean.values())) / min(mean.values())
        ex(f'P3 baseline {lab}: per-min means within 5% ({ {m: round(v/1e6, 1) for m, v in mean.items()} } MB; spread {sp*100:.1f}%)', sp <= 0.05)
for a in by(2) + by(4):
    pass
ex('C1 min 2 and 4: a compaction ran after the enable (10 inputs) and the pending estimate returned to 0', bool(by(2) + by(4)) and all(a['compacted'] >= 1 and a['compacted_inputs'][0] == 10 and a['gauge_last'] == 0 and a['after']['sstables'] == 1 for a in by(2) + by(4)))
ex('C1b min 2 and 4: disk moved above the baseline during the compaction (du max > baseline du + 50 MB)', bool(by(2) + by(4)) and all(a['du_max'] > a['base']['du'] + 50e6 for a in by(2) + by(4)))
def peak(name):
    rows = list(csv.DictReader(open(f'{d}/series-{name}.csv')))
    out = []
    for r in rows:
        out.append(int(r['du']))
        if int(r['compacted_lines']) >= 1:
            break
    return max(out)
if 'c4' in arms and 'c32' in arms:
    c4, c32 = arms['c4'], arms['c32']
    ex(f'C2 control: first compaction takes {c4["compacted_inputs"][:1]} sstables at max=4 and {c32["compacted_inputs"][:1]} at max=32', c4['compacted_inputs'][:1] == [4] and c32['compacted_inputs'][:1] == [10])
    p4, p32 = peak('c4') - c4['base']['du'], peak('c32') - c32['base']['du']
    ex(f'C3 control: peak du above baseline until the first compaction ends: max=4 {p4/1e6:.0f} MB, max=32 {p32/1e6:.0f} MB (ratio {p32/max(p4,1):.1f}, want > 1.8)', p32 > 1.8 * p4)
for a in sorted(arms.values(), key=lambda a: a['name']):
    print('  ', a['name'], 'min', a['min'], 'max', a['max'], 'gauge_max', a['gauge_max'], 'first_pos_s', a['gauge_first_pos_s'], 'last', a['gauge_last'],
          'base(gauge,total,du,heapMB,rssMB)', a['base']['gauge'], a['base']['total'], a['base']['du'], round(a['base']['heap']/1e6, 1), round(a['base']['rss']/1e6, 1),
          'du_max', a['du_max'], 'compacted', a['compacted'], a['compacted_inputs'], 'after', a['after']['sstables'])
