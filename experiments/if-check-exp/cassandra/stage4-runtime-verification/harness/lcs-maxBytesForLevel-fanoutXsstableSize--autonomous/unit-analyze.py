#!/usr/bin/env python3
"""Unit tier analysis for lcs-maxBytesForLevel-fanoutXsstableSize--autonomous: reads readings.txt, judges B2f/B2g.
usage: unit-analyze.py <readings.txt>   -> prints PASS/FAIL per prediction (a FAIL is a reading, not a harness error)"""
import sys, re, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R': R[p[2]] = p[3] if len(p) > 3 else ''
MIB = 1048576
res = []
def chk(name, ok, detail): res.append((name, ok, detail)); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
combos = [(s, f) for s in (1, 2, 4) for f in (2, 10)]
# step 2: L0 bytes ~ 40 MiB for every knob value, ratio scales 1/size, no write error
bad = []; ratios = {}
for s, f in combos:
    for r in (1, 2, 3):
        t = f's{s}f{f}.rep{r}'
        l0 = int(R[t + '.L0bytes']); err = R[t + '.writeError']; ratio = float(R[t + '.L0ratio'])
        if err != 'none' or not (38 * MIB <= l0 <= 46 * MIB): bad.append((t, l0, err))
        ratios[(s, f, r)] = ratio
chk('step2 L0 bytes in 38-46 MiB for all 18 runs, no write error', not bad, str(bad) if bad else 'ok')
for s in (1, 2, 4):
    exp = 42.5e6 / (4 * s * MIB)
    got = [ratios[(s, f, r)] for f in (2, 10) for r in (1, 2, 3)]
    chk(f'step2 L0 ratio at size {s} ~ {exp:.2f}x (scales 1/size)', all(abs(g - exp) / exp < 0.1 for g in got), f'min {min(got)} max {max(got)}')
# step 3: sum of levels after draining ~ ingested (never below), flat across knobs
sums = {}; below = []
for s, f in combos:
    for r in (1, 2, 3):
        t = f's{s}f{f}.rep{r}'
        a = int(R[t + '.sumLevelBytesAfter']); ing = int(R[t + '.ingestedValueBytes'])
        sums[(s, f, r)] = a
        if a < ing: below.append(t)
chk('step3 sum over levels after drain >= ingested value bytes', not below, str(below) if below else 'ok')
lo, hi = min(sums.values()), max(sums.values())
chk('step3 sum over levels after drain flat across the 6 knob pairs (spread < 5%)', hi / lo < 1.05, f'min {lo} max {hi} spread {hi/lo-1:.4f}')
# L1 near target after drain (informational part of B2f: 1.0-1.1)
l1 = [float(R[f's{s}f{f}.rep{r}.L1ratio']) for s, f in combos for r in (1, 2, 3)]
print(f'INFO L1 ratio after drain: min {min(l1)} max {max(l1)}')
# step 4: L8
ok = all(R[f'l8.rep{r}.candidate'] == 'null' and R[f'l8.rep{r}.warnCount'] == '1' and R[f'l8.rep{r}.L8bytes'] == R[f'l8.rep{r}.L8bytesAfter'] and int(R[f'l8.rep{r}.L8bytes']) > int(R[f'l8.rep{r}.L8target']) for r in (1, 2, 3))
chk('step4 L8 over target: null candidate, one WARN, bytes unchanged (3 reps)', ok, '; '.join(f"{R[f'l8.rep{r}.L8bytes']}>{R[f'l8.rep{r}.L8target']}" for r in (1, 2, 3)))
# step 5
mx = [int(R[f'big.rep{r}.maxFile']) for r in (1, 2, 3)]
chk('step5 output sstable > 1 MiB (size knob) for the ~5 MiB partition', all(m > MIB for m in mx), f'maxFile {mx}')
# step 6
chk('step6 arithmetic exact', R['maxBytesForLevel(3,10,160MiB)'] == R['expected(3,10,160MiB)'] and R['maxBytesForLevel(0,10,160MiB)'] == str(4 * 160 * MIB), R['maxBytesForLevel(3,10,160MiB)'])
chk('step6 overflow input throws', R['maxBytesForLevel(8,1000,2^40)'] == 'RuntimeException', R['maxBytesForLevel(8,1000,2^40)'])
# step 7 control
c4 = [int(R[f'mt4.rep{r}.candidates']) for r in (1, 2, 3)]; c32 = [int(R[f'mt32.rep{r}.candidates']) for r in (1, 2, 3)]
chk('step7 control: candidates <= max_threshold (4 and 32), 4 < 32 so it binds', all(c <= 4 for c in c4) and all(c <= 32 for c in c32) and min(c32) > max(c4), f'mt4 {c4} mt32 {c32}')
# truncate control
tr = [R[k] for k in R if k.endswith('sumLevelBytesAfterTruncate')]
chk('control: truncate brings level bytes to 0 in every run', all(t == '0' for t in tr) and len(tr) == 18, f'{len(tr)} runs')
# write refused?
chk('no write refused / exception in any run', all(R[k] == 'none' for k in R if k.endswith('.writeError')), 'ok')
fails = [r for r in res if not r[1]]
print('ALL PREDICTIONS PASS' if not fails else f'{len(fails)} PREDICTION(S) FAIL')
