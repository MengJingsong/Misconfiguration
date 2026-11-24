#!/usr/bin/env python3
# 3-b confirm C10, data-role variant: merged sub-ranges of a SimpleStrategy RF 2 keyspace for a full scan at a CL whose
# blockFor is 2 (QUORUM/TWO/ALL at RF 2): replicas of (t_{i-1}, t_i] = owner(t_i) + the next distinct owner clockwise;
# adjacent ranges merge only when their replica sets are identical (the intersection must hold 2 live replicas,
# ReplicaPlans.maybeMerge), never across the minimum token. Input: '<addr> <token>' lines (C10Load ring).
#   ringcalc-rf2.py <ring-cql.txt> <out-dir>      -> subranges.csv, T_hot (right bound of SR3)
import sys, re
MIN = -2**63
toks = sorted((int(m.group(2)), m.group(1)) for m in (re.match(r'^(127\.0\.0\.\d+)\s+(-?\d+)\s*$', l) for l in open(sys.argv[1])) if m)
assert len(toks) == 48, len(toks)
def reps(i):
    o = toks[i][1]; j = (i + 1) % len(toks)
    while toks[j][1] == o: j = (j + 1) % len(toks)
    return frozenset((o, toks[j][1]))
vr = [(MIN, toks[0][0], reps(0))] + [(toks[k - 1][0], toks[k][0], reps(k)) for k in range(1, len(toks))] + [(toks[-1][0], MIN, reps(0))]
sr = []
for lo, hi, rs in vr:
    if sr and sr[-1][2] == rs and sr[-1][1] != MIN: sr[-1] = (sr[-1][0], hi, rs, sr[-1][3] + 1)
    else: sr.append((lo, hi, rs, 1))
out = sys.argv[2]
with open(out + '/subranges.csv', 'w') as f:
    f.write('sr,left,right,replicas,vnodes\n')
    for i, (lo, hi, rs, n) in enumerate(sr, 1): f.write(f'{i},{lo},{hi},{"+".join(sorted(rs))},{n}\n')
open(out + '/T_hot', 'w').write(str(sr[2][1]) + '\n')
n1 = sum(1 for s in sr[3:] if '127.0.0.1' in s[2])
print(f'vnode ranges={len(vr)} merged S={len(sr)} (blockFor 2) SR1 vnodes={sr[0][3]} SR1-3 replicas={["+".join(sorted(s[2])) for s in sr[:3]]} '
      f'dense D={len(sr) - 3}, of which node 1 is a replica of {n1}; T_hot={sr[2][1]}')
