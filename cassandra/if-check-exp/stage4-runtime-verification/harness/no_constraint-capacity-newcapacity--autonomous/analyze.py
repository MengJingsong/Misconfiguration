#!/usr/bin/env python3
"""Judge raw-all.csv against the frozen prediction of no_constraint-capacity-newcapacity--autonomous (B2 amendment 2026-10-29 + correction, item e).
Usage: analyze.py <raw-all.csv>. Rep 0 of each JVM is the discarded warm-up."""
import sys, collections
keys = 'mode c arm rep cap0 target usedAlloc ovfAlloc poolAlloc u0 o0 d0 sc u128 o128 capNew u1 o1 d1 p1 d2 u2 o2 heap exc'.split()
rows = []; cache = None
for ln in open(sys.argv[1]):
    ln = ln.strip()
    if ln.startswith('#'):
        cache = ln.split('cache=')[1].split()[0]; continue
    f = ln.split(','); r = dict(zip(keys, f))
    for k in keys:
        if k not in ('mode', 'arm', 'exc'): r[k] = int(r[k])
    r['cache'] = cache; rows.append(r)
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
sw = [r for r in rows if r['mode'] == 'sweep' and r['rep'] >= 1]
Cs = sorted(set(r['c'] for r in sw)); print('C values:', Cs, 'counted rows:', len(sw))
for C in Cs:
    ov = C >= (1 << 20)
    R = {a: [r for r in sw if r['c'] == C and r['arm'] == a] for a in 'EGSM'}
    for a in 'EGSM': chk(f'C={C} {a}: 5 repetitions', len(R[a]) == 5)
    allr = [r for a in 'EGSM' for r in R[a]]
    chk(f'C={C}: allocation state used==cap0, overflow==cap0 (overflow sizes) else 0', all(r['usedAlloc'] == r['cap0'] and r['ovfAlloc'] == (r['cap0'] if ov else 0) for r in allr), f"cap0={allr[0]['cap0']}")
    if ov: chk(f'C={C}: cap0 == C (overflow buffer exact)', all(r['cap0'] == C for r in allr))
    chk(f'C={C}: after release used==0 and overflow==0 (all arms)', all(r['u2'] == 0 and r['o2'] == 0 for r in allr))
    E = R['E']
    chk(f'C={C} E: SC=0, gauges unchanged, capacity unchanged', all(r['sc'] == 0 and r['u1'] == r['u0'] and r['o1'] == r['o0'] and r['d1'] == r['d0'] and r['capNew'] == r['cap0'] for r in E))
    chk(f'C={C} E: residue <= 1024', all(r['heap'] <= 1024 for r in E), f"max {max(r['heap'] for r in E)}")
    if ov: chk(f'C={C} E: direct delta 0 after gc', all(r['d2'] - r['d0'] == 0 for r in E), str([r['d2'] - r['d0'] for r in E]))
    G = R['G']
    chk(f'C={C} G: SC=1 and capNew in [cap0+1, bound]', all(r['sc'] == 1 and r['capNew'] >= r['cap0'] + 1 and (r['capNew'] == r['cap0'] + 1 if ov else r['capNew'] <= r['cap0'] + 2048) for r in G), f"cap0={G[0]['cap0']} capNew={G[0]['capNew']}")
    chk(f'C={C} G: used after == capNew (one buffer), overflow after as predicted', all(r['u1'] == r['capNew'] and r['o1'] == (r['capNew'] if ov else 0) for r in G))
    chk(f'C={C} G: line-128 record used == cap0+capNew (both held)', all(r['u128'] == r['cap0'] + r['capNew'] for r in G), str([(r['u128'], r['cap0'] + r['capNew']) for r in G[:1]]))
    chk(f'C={C} G: residue <= 16384', all(r['heap'] <= 16384 for r in G), f"max {max(r['heap'] for r in G)}")
    if ov:
        chk(f'C={C} G: direct delta after call == capNew', all(r['d1'] - r['d0'] == r['capNew'] for r in G), str([r['d1'] - r['d0'] for r in G[:2]]))
        chk(f'C={C} G: direct delta after gc within 4096 of capNew-cap0', all(abs((r['d2'] - r['d0']) - (r['capNew'] - r['cap0'])) <= 4096 for r in G), str([r['d2'] - r['d0'] for r in G[:2]]))
    S = R['S']
    chk(f'C={C} S: SC=1, used after == capNew <= cap0/2+2048, line-128 == cap0+capNew', all(r['sc'] == 1 and r['u1'] == r['capNew'] and r['capNew'] <= r['cap0'] // 2 + 2048 and r['u128'] == r['cap0'] + r['capNew'] for r in S), f"capNew={S[0]['capNew']}")
    chk(f'C={C} S: residue <= 16384', all(r['heap'] <= 16384 for r in S), f"max {max(r['heap'] for r in S)}")
    M = R['M']
    chk(f'C={C} M: IllegalArgumentException, SC=1, usage unchanged', all(r['exc'] == 'IllegalArgumentException' and r['sc'] == 1 and r['u1'] == r['u0'] and r['o1'] == r['o0'] and r['capNew'] == r['cap0'] for r in M))
# controls
ctl = lambda cache, c: [r for r in rows if r['mode'] == 'control' and r['cache'] == cache and r['c'] == c and r['rep'] >= 1]
a = ctl('128', 4096); b = ctl('0', 4096); k = ctl('128', 16777216)
chk('control cache=128, C=4096: pooled bytes 8388608, overflow 0', len(a) == 5 and all(r['poolAlloc'] == 8388608 and r['ovfAlloc'] == 0 for r in a), str([(r['poolAlloc'], r['ovfAlloc']) for r in a[:1]]))
chk('control cache=0, C=4096: pooled bytes 0, overflow == cap0 (4096)', len(b) == 5 and all(r['poolAlloc'] == 0 and r['ovfAlloc'] == r['cap0'] == 4096 for r in b), str([(r['poolAlloc'], r['ovfAlloc']) for r in b[:1]]))
chk('known answer C=16 MiB: overflow == 16777216', len(k) == 5 and all(r['ovfAlloc'] == 16777216 for r in k))
print('SUMMARY %d PASS, %d FAIL' % (sum(res), len(res) - sum(res)))
sys.exit(0 if all(res) else 1)
