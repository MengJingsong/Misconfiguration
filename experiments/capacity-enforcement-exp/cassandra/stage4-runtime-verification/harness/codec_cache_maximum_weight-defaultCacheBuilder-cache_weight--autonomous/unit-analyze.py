#!/usr/bin/env python3
# Unit-tier analysis for order 96 (B2f/B2g with S4-A4 rules). Usage: unit-analyze.py <raw/unit dir>
import glob, os, re, statistics, sys
d = sys.argv[1]
cells = {}   # (cell, checkpoint) -> list of dicts
for f in sorted(glob.glob(os.path.join(d, 'probe-*.txt'))):
    tag = os.path.basename(f)[6:-4]
    if tag.startswith('smoke'):
        continue
    cell = re.sub(r'-r\d$', '', tag)
    for line in open(f):
        m = re.search(r'PROBE (\S+) size=(\d+) weight=(\d+) deepBytes=(\d+) heapUsed=(\d+)', line)
        if m:
            cp = m.group(1)
            cells.setdefault((cell, cp), []).append(dict(size=int(m.group(2)), weight=int(m.group(3)),
                                                        deep=int(m.group(4)), heap=int(m.group(5)), tag=tag))
        m = re.search(r'PROBE B list<int> still cached: (\w+)', line)
        if m:
            cells.setdefault((cell, 'B-list-int-cached'), []).append(dict(val=m.group(1), tag=tag))

med = {}
print('| cell | checkpoint | n | size (med; all) | weight (med; all) | deepBytes (med; all) | heapUsed (med) |')
print('|---|---|---|---|---|---|---|')
for (cell, cp), rows in sorted(cells.items()):
    if cp == 'B-list-int-cached':
        print(f'| {cell} | list<int> still cached | {len(rows)} | {", ".join(r["val"] for r in rows)} | | | |')
        med[(cell, cp)] = [r['val'] for r in rows]
        continue
    m = {k: statistics.median(r[k] for r in rows) for k in ('size', 'weight', 'deep', 'heap')}
    med[(cell, cp)] = m
    def al(k): return '/'.join(str(r[k]) for r in rows)
    print(f'| {cell} | {cp} | {len(rows)} | {m["size"]:.0f} ({al("size")}) | {m["weight"]:.0f} ({al("weight")}) | '
          f'{m["deep"]:.0f} ({al("deep")}) | {m["heap"]:.0f} |')

def g(cell, cp): return med.get((cell, cp))
print()
print('## Rule evaluation (S4-A4)')
A = {k: g(f'A-cap1000-k{k}', f'A-k{k}') for k in (500, 1000, 2000, 5000)}
C = {m: g(f'C-cap1000-m{m}-k2000', f'C-m{m}-k2000') for m in (1, 1000, 10000)}
B0 = g('B-cap1000', 'B-zero-only'); B1 = g('B-cap1000', 'B-zero-plus-5000-vectors')
Bl = g('B-cap1000', 'B-list-int-cached')
p100 = g('A-cap100-k2000', 'A-k2000'); p10k = g('A-cap10000-k12000', 'A-k12000')
c100 = g('C-cap100-m1000-k2000', 'C-m1000-k2000'); c10k = g('C-cap10000-m1000-k2000', 'C-m1000-k2000')
out = []
if all(A.values()):
    pl_size = abs(A[5000]['size'] - A[2000]['size']) <= 0.1 * A[2000]['size']
    pl_deep = abs(A[5000]['deep'] - A[2000]['deep']) <= 0.1 * A[2000]['deep']
    out.append(f"W-A plateau (K=2000 vs 5000 within ±10 %): size {A[2000]['size']:.0f}->{A[5000]['size']:.0f} {pl_size}; "
               f"deepBytes {A[2000]['deep']:.0f}->{A[5000]['deep']:.0f} {pl_deep}; size at K=2000/5000 in 950-1000: "
               f"{950 <= A[2000]['size'] <= 1000 and 950 <= A[5000]['size'] <= 1000}; never plateaus (size grows to K): {A[5000]['size'] >= 4500}")
    out.append(f"W-A bytes per entry at plateau: {A[2000]['deep']/A[2000]['size']:.1f} B; K=500: {A[500]['deep']/max(A[500]['size'],1):.1f} B")
if all(C.values()):
    r = C[10000]['deep'] / C[1]['deep']
    out.append(f"W-C size/weight: M=1 {C[1]['size']:.0f}/{C[1]['weight']:.0f}, M=1000 {C[1000]['size']:.0f}/{C[1000]['weight']:.0f}, "
               f"M=10000 {C[10000]['size']:.0f}/{C[10000]['weight']:.0f}")
    out.append(f"W-C deepBytes: M=1 {C[1]['deep']:.0f}, M=1000 {C[1000]['deep']:.0f}, M=10000 {C[10000]['deep']:.0f}; "
               f"ratio M=10000/M=1 = {r:.1f} (>=100 -> row 1 confirmed; <=2 -> bounded by weight, refuted)")
    for m in (1, 1000, 10000):
        pred = {1: 0.2e6, 1000: 4e6, 10000: 40e6}[m]
        out.append(f"  W-C M={m}: deepBytes {C[m]['deep']/1e6:.2f} MB vs predicted ≈{pred/1e6:g} MB, within [0.5X,2X]: {0.5*pred <= C[m]['deep'] <= 2*pred}; bytes/entry {C[m]['deep']/C[m]['size']:.0f}")
if B0 and B1:
    out.append(f"W-B: zero-only size={B0['size']:.0f} weight={B0['weight']:.0f}; +5000 vectors size={B1['size']:.0f} weight={B1['weight']:.0f}; "
               f"list<int> still cached: {Bl}; zero-weight entries kept and not counted: {B0['size'] == 440 and B0['weight'] == 0 and B1['size'] - B1['weight'] == 440}")
if p100 and p10k:
    out.append(f"Knob (narrow): cap100 K=2000 size={p100['size']:.0f} weight={p100['weight']:.0f} deep={p100['deep']:.0f}; "
               f"cap10000 K=12000 size={p10k['size']:.0f} weight={p10k['weight']:.0f} deep={p10k['deep']:.0f}; "
               f"cap1000 K=2000 deep={A[2000]['deep']:.0f}; positive control moves (cap100 size<=110 and cap10000 size>=9000): "
               f"{p100['size'] <= 110 and p10k['size'] >= 9000}; deep ratio cap100/cap1000 {p100['deep']/A[2000]['deep']:.3f}, cap10000/cap1000 {p10k['deep']/A[2000]['deep']:.2f}")
if c100 and c10k:
    out.append(f"Knob (wide M=1000): cap100 size={c100['size']:.0f} weight={c100['weight']:.0f} deep={c100['deep']/1e6:.2f} MB; "
               f"cap10000 size={c10k['size']:.0f} weight={c10k['weight']:.0f} deep={c10k['deep']/1e6:.2f} MB; cap1000 deep={C[1000]['deep']/1e6:.2f} MB")
    out.append(f"  bytes per weight unit at M=1000: cap100 {c100['deep']/c100['weight']:.0f}, cap1000 {C[1000]['deep']/C[1000]['weight']:.0f}, cap10000 {c10k['deep']/c10k['weight']:.0f}; at M=1 cap1000 {C[1]['deep']/C[1]['weight']:.0f}")
print('\n'.join('- ' + o for o in out))
