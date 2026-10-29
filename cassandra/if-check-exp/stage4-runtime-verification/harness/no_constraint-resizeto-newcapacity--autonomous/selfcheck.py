#!/usr/bin/env python3
"""Independent re-parse of raw-all.csv (csv module, own expected values from a re-derivation, not analyze.py's code).
Usage: selfcheck.py <raw-all.csv>"""
import csv, sys
rows = [l for l in csv.reader(open(sys.argv[1])) if l and not l[0].startswith('#')]
hdr = ['mode','c','arm','rep','capB','lenB','copies','allocs','aB','frees','fB','peak','live','capA','lenA','heap','rb']
R = [dict(zip(hdr, l)) for l in rows]
for r in R:
    for k in hdr:
        if k not in ('mode', 'arm'): r[k] = int(r[k])
ok = 0; bad = 0
def hold(name, c):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print('FAIL', name)
# expectation re-derived: what trim()/copy would do to a region of cap C holding f bytes
def expect(arm, C):
    if arm == 'E': return dict(allocs=0, aB=0, peak=C, live=C, capA=C)
    if arm == 'D': return dict(allocs=1, aB=C-1, peak=C + C - 1, live=C-1, capA=C-1)
    if arm == 'H': return dict(allocs=1, aB=C//2, peak=C + C//2, live=C//2, capA=C//2)
    if arm == 'X': return dict(allocs=1, aB=C, peak=2*C, live=C, capA=C)
for r in R:
    if r['mode'] != 'sweep' or r['rep'] == 0: continue
    e = expect(r['arm'], r['c'])
    hold(f"{r['c']} {r['arm']} {r['rep']} fields", all(r[k] == v for k, v in e.items()))
    hold(f"{r['c']} {r['arm']} {r['rep']} ledger live-after == capacity-after", r['live'] == r['capA'])
    hold(f"{r['c']} {r['arm']} {r['rep']} frees balance", r['frees'] == r['allocs'] and (r['allocs'] == 0 or r['fB'] == r['c']))
cs = sorted(set(r['c'] for r in R if r['mode'] == 'sweep'))
for C in cs:
    for rep in range(1, 6):
        d = {r['arm']: r for r in R if r['mode'] == 'sweep' and r['c'] == C and r['rep'] == rep}
        hold(f'{C} rep{rep} E vs D retained differ by 1', d['E']['capA'] - d['D']['capA'] == 1)
        hold(f'{C} rep{rep} E vs X: X skips exactly C bytes, peak gap C', d['X']['aB'] - d['E']['aB'] == C and d['X']['peak'] - d['E']['peak'] == C)
ctl = {}
for r in R:
    if r['mode'] == 'control' and r['rep'] >= 1: ctl.setdefault(r['aB'], 0); ctl[r['aB']] += 1
hold('control: two distinct allocation sizes (16777216 and 12582912), 5 each', ctl == {16777216: 5, 12582912: 5}, )
print('SELFCHECK %d hold, %d fail' % (ok, bad))
sys.exit(1 if bad else 0)
