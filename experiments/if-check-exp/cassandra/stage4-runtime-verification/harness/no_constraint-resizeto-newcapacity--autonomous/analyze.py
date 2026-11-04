#!/usr/bin/env python3
"""Judge raw-all.csv against the frozen prediction of no_constraint-resizeto-newcapacity--autonomous (B2 amendment 2026-10-29, item e).
Usage: analyze.py <raw-all.csv>.  Rep 0 of each JVM is the discarded warm-up."""
import sys, collections
rows = []
dob = {}
mode_hdr = None
for ln in open(sys.argv[1]):
    ln = ln.strip()
    if ln.startswith('#'):
        if 'dob=' in ln:
            mode_hdr = ln.split('dob=')[1].split()[0]
        continue
    f = ln.split(',')
    keys = 'mode c arm rep capBefore lenBefore copies allocs allocBytes frees freeBytes peak liveAfter capAfter lenAfter heap rb'.split()
    r = dict(zip(keys, f)); 
    for k in keys[1:2]+keys[3:]: r[k] = int(r[k])
    r['dob'] = mode_hdr
    rows.append(r)
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
sw = [r for r in rows if r['mode'] == 'sweep' and r['rep'] >= 1]
Cs = sorted(set(r['c'] for r in sw))
print('C values:', Cs, ' counted rows:', len(sw))
resid = collections.defaultdict(list)
for C in Cs:
    for arm in 'EDHX':
        rs = [r for r in sw if r['c'] == C and r['arm'] == arm]
        chk(f'C={C} {arm}: 5 repetitions', len(rs) == 5, str(len(rs)))
        if arm == 'E':
            ok = all(r['copies'] == 0 and r['allocs'] == 0 and r['allocBytes'] == 0 and r['frees'] == 0 and r['peak'] == C and r['liveAfter'] == C and r['capAfter'] == C for r in rs)
        elif arm == 'D':
            ok = all(r['copies'] == 1 and r['allocs'] == 1 and r['allocBytes'] == C - 1 and r['frees'] == 1 and r['freeBytes'] == C and r['peak'] == 2 * C - 1 and r['liveAfter'] == C - 1 and r['capAfter'] == C - 1 and r['rb'] == 1 for r in rs)
        elif arm == 'H':
            ok = all(r['copies'] == 1 and r['allocBytes'] == C // 2 and r['peak'] == C + C // 2 and r['liveAfter'] == C // 2 and r['capAfter'] == C // 2 and r['rb'] == 1 for r in rs)
        else:
            ok = all(r['allocBytes'] == C and r['peak'] == 2 * C and r['liveAfter'] == C and r['capAfter'] == C for r in rs)
        chk(f'C={C} {arm}: native figures exact', ok, str([(r['allocBytes'], r['peak'], r['liveAfter'], r['capAfter']) for r in rs[:1]]))
        resid[arm] += [(C, r['heap']) for r in rs]
        lim = 1024 if arm == 'E' else 16384
        chk(f'C={C} {arm}: residue <= {lim}', all(r['heap'] <= lim for r in rs), f"max {max(r['heap'] for r in rs)}")
    e = [r for r in sw if r['c'] == C and r['arm'] == 'E']; d = [r for r in sw if r['c'] == C and r['arm'] == 'D']
    chk(f'C={C}: retained E - D = 1 byte', all(a['capAfter'] - b['capAfter'] == 1 for a, b in zip(e, d)))
    x = [r for r in sw if r['c'] == C and r['arm'] == 'X']
    chk(f'C={C}: retained E == X', all(a['capAfter'] == b['capAfter'] for a, b in zip(e, x)))
for arm in 'EDHX':
    per = collections.defaultdict(list)
    for C, h in resid[arm]: per[C].append(h)
    hi = max(max(v) for v in per.values()); lo = min(min(v) for v in per.values())
    chk(f'{arm}: residue spread over all C (max-min) <= 4096', hi - lo <= 4096, f'max {hi} min {lo} spread {hi-lo}')
# noise floor: native spread
chk('noise floor: native allocBytes identical over 5 reps per arm and C', all(len(set(r['allocBytes'] for r in sw if r['c'] == C and r['arm'] == a)) == 1 for C in Cs for a in 'EDHX'))
# control
ctl = [r for r in rows if r['mode'] == 'control' and r['rep'] >= 1]
for d, want in (('null', 16777216), ('1', 12582912)):
    rs = [r for r in ctl if r['dob'] == d]
    chk(f'control dob={d}: allocBytes == {want} in all reps', len(rs) == 5 and all(r['allocBytes'] == want and r['capAfter'] == want for r in rs), str([r['allocBytes'] for r in rs]))
a = [r for r in ctl if r['dob'] == 'null']; b = [r for r in ctl if r['dob'] == '1']
chk('control moved by exactly 4194304', bool(a) and bool(b) and a[0]['allocBytes'] - b[0]['allocBytes'] == 4194304)
print('SUMMARY %d PASS, %d FAIL' % (sum(res), len(res) - sum(res)))
sys.exit(0 if all(res) else 1)
