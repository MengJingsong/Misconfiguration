#!/usr/bin/env python3
"""Unit tier analysis for sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous: judges B2f/B2g from readings.txt."""
import sys, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R': R[p[2]] = p[3] if len(p) > 3 else ''
MIB = 1048576; res = []
def chk(name, ok, detail): res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
for n in (1, 5, 20, 160):
    got = {d: (R[f'N{n}.single[{d}].nextLevel'], R[f'N{n}.three[{d}].nextLevel'], R[f'N{n}.single[{d}].totalBytes']) for d in (-1, 0, 1)}
    exp = {-1: '0', 0: '1', 1: '1'}
    chk(f'boundary N={n}: totals N MiB-1 -> 0; N MiB -> 1; N MiB+1 -> 1 (single and 3-way split)', all(got[d][0] == exp[d] and got[d][1] == exp[d] and int(got[d][2]) == n * MIB + d for d in got), str(got))
    chk(f'mixed L0+L1 -> 1, all-L1 -> 2 at N={n}', R[f'N{n}.mixedL0L1.nextLevel'] == '1' and R[f'N{n}.allL1.nextLevel'] == '2', f"{R[f'N{n}.mixedL0L1.nextLevel']}, {R[f'N{n}.allL1.nextLevel']}")
for n in (1, 5, 20):
    a = [(R[f'N{n}.setA.rep{r}.nextLevel'], float(R[f'N{n}.setA.rep{r}.total/size'])) for r in (1, 2, 3)]
    b = [(R[f'N{n}.setB.rep{r}.nextLevel'], float(R[f'N{n}.setB.rep{r}.total/size'])) for r in (1, 2, 3)]
    chk(f'sets N={n}: Set A (<N) -> 0, Set B (>N) -> 1', all(l == '0' and t < 1 for l, t in a) and all(l == '1' and t > 1 for l, t in b), f'A {a} B {b}')
a = [(R[f'N160.setA.rep{r}.nextLevel'], R[f'N160.setB.rep{r}.nextLevel'], float(R[f'N160.setB.rep{r}.total/size'])) for r in (1, 2, 3)]
chk('sets N=160: both sets far below -> level 0, single output', all(x[0] == '0' and x[1] == '0' and x[2] < 1 for x in a) and all(R[f'N160.setB.rep{r}.outputs'] == '1' for r in (1, 2, 3)), str(a))
# Set B compaction outputs
sums = {}
for n in (1, 5, 20, 160):
    outs = []; 
    for r in (1, 2, 3):
        sz = eval(R[f'N{n}.setB.rep{r}.outputSizes']); inb = int(R[f'N{n}.setB.rep{r}.totalBytes']); sums.setdefault(n, []).append(int(R[f'N{n}.setB.rep{r}.outputSum']) / inb)
        outs.append((len(sz), max(sz) / MIB, eval(R[f'N{n}.setB.rep{r}.outputLevels'])))
    print(f'INFO N={n} Set B outputs (count, max MiB, levels): {outs}')
for n in (1, 5, 20):
    ok = all(len(eval(R[f'N{n}.setB.rep{r}.outputSizes'])) >= 1 and max(eval(R[f'N{n}.setB.rep{r}.outputSizes'])) <= n * MIB + 200 * 1024 for r in (1, 2, 3))
    chk(f'Set B output files at N={n}: each <= N MiB + 200 KiB (one partition)', ok, 'ok')
cnt = {n: [int(R[f'same.N{n}.rep{r}.outputs']) for r in (1, 2, 3)] for n in (1, 5, 20, 160)}
chk('positive control (B2h, same ~30 MiB input at every N): output file count grows as N shrinks', all(cnt[1][i] > cnt[5][i] > cnt[20][i] > cnt[160][i] for i in range(3)), str(cnt))
sm = [int(R[f'same.N{n}.rep{r}.outputSum']) / int(R[f'same.N{n}.rep{r}.inputBytes']) for n in (1, 5, 20, 160) for r in (1, 2, 3)]
chk('same-input control: total output bytes ~ input bytes at every N (< 2% apart)', max(sm) / min(sm) < 1.02, f'{min(sm):.4f}..{max(sm):.4f}')
allsum = [x for v in sums.values() for x in v]
chk('sum of outputs vs inputs differs by < 10% across all N', max(allsum) / min(allsum) < 1.1 and min(allsum) > 0.9, f'{min(allsum):.4f}..{max(allsum):.4f}')
mx = [int(R[f'big5.rep{r}.maxFile']) for r in (1, 2, 3)]
chk('oversized (~15 MiB) partition at N=5: one output file > 5 MiB', all(m > 5 * MIB for m in mx), str(mx))
print('ALL PREDICTIONS PASS' if all(res) else f'{res.count(False)} PREDICTION(S) FAIL')
