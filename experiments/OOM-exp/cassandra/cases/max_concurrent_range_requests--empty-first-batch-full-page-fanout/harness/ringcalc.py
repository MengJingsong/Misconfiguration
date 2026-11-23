#!/usr/bin/env python3
# C10: merged sub-ranges from `nodetool ring` (RF 1, SimpleStrategy, CL ONE), as ReplicaPlanIterator + ReplicaPlanMerger
# would form them for a full scan (min, min]: vnode ranges (t_{i-1}, t_i] owned by owner(t_i), the first piece
# (MIN, t_0] owned by owner(t_0) and the last (t_last, MIN] owned by owner(t_0); adjacent ranges with the same owner
# merge (never across the minimum token). Prints subranges.csv and T_hot = right bound of SR3.
#   ringcalc.py <ring.txt> <out-dir>
import sys, re
MIN = -2**63
toks = []
for line in open(sys.argv[1]):
    m = re.match(r'^(127\.0\.0\.\d+)\s+\S+\s+(Up|Down)\s+\S+\s+.*\s(-?\d+)\s*$', line)
    if m: toks.append((int(m.group(3)), m.group(1)))
toks.sort()
assert len(toks) == 48, f'expected 48 tokens, got {len(toks)}'
vr = [(MIN, toks[0][0], toks[0][1])]
for k in range(1, len(toks)): vr.append((toks[k - 1][0], toks[k][0], toks[k][1]))
vr.append((toks[-1][0], MIN, toks[0][1]))  # wraps to the minimum token: last range
sr = []
for lo, hi, ow in vr:
    if sr and sr[-1][2] == ow and sr[-1][1] != MIN:
        sr[-1] = (sr[-1][0], hi, ow, sr[-1][3] + 1)
    else:
        sr.append((lo, hi, ow, 1))
out = sys.argv[2]
with open(out + '/subranges.csv', 'w') as f:
    f.write('sr,left,right,owner,vnodes\n')
    for i, (lo, hi, ow, n) in enumerate(sr, 1): f.write(f'{i},{lo},{hi},{ow},{n}\n')
thot = sr[2][1]
open(out + '/T_hot', 'w').write(str(thot) + '\n')
own = {}
for s in sr[3:]: own[s[2]] = own.get(s[2], 0) + 1
print(f'vnode ranges={len(vr)} merged S={len(sr)} SR1 vnodes={sr[0][3]} SR1-3 owners={[s[2] for s in sr[:3]]} '
      f'dense D={len(sr)-3} by owner={own} T_hot={thot}')
