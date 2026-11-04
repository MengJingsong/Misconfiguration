#!/usr/bin/env python3
"""Unit tier analysis for sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous: judges B2f/B2g from readings.txt."""
import sys, collections
R = collections.OrderedDict()
for l in open(sys.argv[1]):
    p = l.rstrip('\n').split(' ', 3)
    if p[0] == 'R': R[p[2]] = p[3] if len(p) > 3 else ''
MIB = 1048576; res = []
def chk(name, ok, detail): res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ' :: ' + detail)
for n in (1, 5):
    g = [(R[f'N{n}.rep{r}.candidateHasL1'], int(R[f'N{n}.rep{r}.candidateBytes']), float(R[f'N{n}.rep{r}.l0total/size'])) for r in (1, 2, 3)]
    chk(f'phase1 N={n}: L0 total > size and the candidate set contains the L1 sstable (3 reps)', all(h == 'true' and b > n * MIB and t > 1 for h, b, t in g), str(g))
g = [(R[f'N160.rep{r}.candidateHasL1'], R[f'N160.rep{r}.candidateOutputLevel'], float(R[f'N160.rep{r}.l0total/size'])) for r in (1, 2, 3)]
chk('phase1 N=160: L0 total < size, no L1 sstable in the candidate set, output level 0 (3 reps)', all(h == 'false' and lv == '0' and t < 1 for h, lv, t in g), str(g))
for n in (1, 5, 160):
    chk(f'phase1 N={n}: candidate carries maxSSTableBytes = N MiB', all(R[f'N{n}.rep{r}.candidateMaxSSTableBytes'] == str(n * MIB) for r in (1, 2, 3)), R[f'N{n}.rep1.candidateMaxSSTableBytes'])
# step 4
for r in (1, 2, 3):
    sizes = eval(R[f'out5.rep{r}.outputSizes']); inb = int(R[f'out5.rep{r}.inputBytes'])
    chk(f'step4 rep{r}: size-5 task splits {inb/MIB:.1f} MiB into >=2 files, each <= 5 MiB + 200 KiB (one partition)', len(sizes) >= 2 and max(sizes) <= 5 * MIB + 200 * 1024, str(sizes))
    chk(f'step4 rep{r}: single ~12 MiB partition gives one file > 5 MiB', int(R[f'big5.rep{r}.maxFile']) > 5 * MIB and R[f'big5.rep{r}.outputs'] == '1', f"maxFile {R[f'big5.rep{r}.maxFile']} outputs {R[f'big5.rep{r}.outputs']}")
# phase 2
l1 = [int(R[f'p1.rep{r}.L0bytes']) for r in (1, 2, 3)]; l160 = [int(R[f'p160.rep{r}.L0bytes']) for r in (1, 2, 3)]
chk('phase2 L0 total ~ 200 MiB at size 1 and 160, all sstables level 0', all(190 * MIB < x < 230 * MIB for x in l1 + l160) and all(R[f'{t}.rep{r}.notL0'] == '0' for t in ('p1', 'p160') for r in (1, 2, 3)), f'p1 {l1} p160 {l160}')
chk('phase2 L0 total does not depend on the option (|p1-p160| < 2%)', all(abs(a - b) / a < 0.02 for a, b in zip(l1, l160)), 'ok')
chk('phase2 L0 total exceeds the L0 cap formula 4 x size at size 1 (4 MiB) and 160 (640 MiB)? (160: no, 200 MiB < 640)', min(l1) > 4 * MIB and max(l160) < 640 * MIB, f'p160 max {max(l160)} vs 640 MiB: limit NOT reached at 160')
tr = [R[k] for k in R if k.endswith('bytesAfterTruncate')]
chk('control: truncate brings table bytes to 0', all(t == '0' for t in tr) and len(tr) == 6, str(tr))
print('ALL PREDICTIONS PASS' if all(res) else f'{res.count(False)} PREDICTION(S) FAIL')
