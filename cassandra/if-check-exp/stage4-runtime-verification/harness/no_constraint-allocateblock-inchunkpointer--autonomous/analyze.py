#!/usr/bin/env python3
"""Judge raw-all.csv against the frozen prediction of no_constraint-allocateblock-inchunkpointer--autonomous (B2 amendment 2026-10-29, item e).
Usage: analyze.py <raw-all.csv>. Rep 0 of the sweep JVM is the discarded warm-up."""
import sys, collections
keys = 'mode type i rep call N S pos0 pos1 soh0 soh1 ret0 ret1 nullb cap d0 d1 heap exc R'.split()
rows = []
for ln in open(sys.argv[1]):
    ln = ln.strip()
    if ln.startswith('#'): continue
    f = ln.split(','); r = dict(zip(keys, f))
    for k in keys:
        if k not in ('mode', 'type', 'call', 'exc'): r[k] = int(r[k])
    rows.append(r)
res = []
def chk(name, ok, detail=''):
    res.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (' :: ' + detail if detail else ''))
sw = [r for r in rows if r['mode'] == 'sweep' and r['rep'] >= 1]
get = lambda t, i, c: [r for r in sw if r['type'] == t and r['i'] == i and r['call'] == c]
resid = {}
for i in (1, 3, 7, 11, 15, 19):
    F, A, B = get('ON_HEAP', i, 'F'), get('ON_HEAP', i, 'A'), get('ON_HEAP', i, 'B')
    N = 256 << i; S = 256 * ((1 << i) - 1)
    chk(f'i={i}: 5 repetitions of F, A, B', len(F) == len(A) == len(B) == 5)
    chk(f'i={i}: floor (empty window) <= 1024', all(r['heap'] <= 1024 for r in F), f"max {max(r['heap'] for r in F)}")
    chk(f'i={i} A: no buffer (<= 1024 B), positions, buffers[i] null', all(r['heap'] <= 1024 and r['pos0'] == S - 32 and r['pos1'] == S and r['nullb'] == 1 and r['cap'] == -1 for r in A), f"heap {[r['heap'] for r in A]}")
    chk(f'i={i} A: sizeOnHeap delta == 32+R, retained == S', all(r['soh1'] - r['soh0'] == 32 + r['R'] and r['ret0'] == S and r['ret1'] == S for r in A), f"delta {A[0]['soh1']-A[0]['soh0']} R {A[0]['R']}")
    chk(f'i={i} B: bytes in [N+16, N+512]', all(N + 16 <= r['heap'] <= N + 512 for r in B), f"N={N} B={[r['heap'] for r in B]}")
    chk(f'i={i} B: positions, buffers[i] allocated with capacity N', all(r['pos0'] == S and r['pos1'] == S + 32 and r['nullb'] == 1 and r['cap'] == N for r in B))
    chk(f'i={i} B: sizeOnHeap delta == 32, retained == S+N', all(r['soh1'] - r['soh0'] == 32 and r['ret0'] == S and r['ret1'] == S + N for r in B), f"ratio retained/pos {B[0]['ret1']/B[0]['pos1']:.3f}")
    chk(f'i={i}: B - A in [N, N+512]', all(N <= b['heap'] - a['heap'] <= N + 512 for a, b in zip(A, B)))
    chk(f'i={i}: noise, spread over 5 reps <= 256 (A and B)', max(r['heap'] for r in A) - min(r['heap'] for r in A) <= 256 and max(r['heap'] for r in B) - min(r['heap'] for r in B) <= 256)
    resid[i] = sorted(r['heap'] - N for r in B)[2]
chk('residue (B - N) differs between values of i by <= 256', max(resid.values()) - min(resid.values()) <= 256, str(resid))
for i in (11, 15):
    A, B = get('OFF_HEAP', i, 'A'), get('OFF_HEAP', i, 'B'); N = 256 << i
    chk(f'OFF_HEAP i={i}: direct gauge delta A == 0, B == N', len(A) == len(B) == 5 and all(r['d1'] - r['d0'] == 0 for r in A) and all(r['d1'] - r['d0'] == N for r in B), str([r['d1'] - r['d0'] for r in B]))
    chk(f'OFF_HEAP i={i}: B thread bytes <= 1024 (buffer invisible)', all(r['heap'] <= 1024 for r in B), str([r['heap'] for r in B]))
ob = [get('OFF_HEAP', i, 'B')[0]['heap'] for i in (11, 15)]
chk('OFF_HEAP: B thread bytes equal at i=11 and 15 within 256', abs(ob[0] - ob[1]) <= 256, str(ob))
c = {r['call']: r for r in rows if r['mode'] == 'control'}
chk('control A (i=22): <= 1024, B in [2^30+16, 2^30+512]', 'A' in c and 'B' in c and c['A']['heap'] <= 1024 and (1 << 30) + 16 <= c['B']['heap'] <= (1 << 30) + 512, f"A={c.get('A',{}).get('heap')} B={c.get('B',{}).get('heap')}")
chk('control C1: advance to S_23 allocates <= 1024, allocatedPos == 2147483392', 'C1' in c and c['C1']['heap'] <= 1024 and c['C1']['pos1'] == 2147483392, f"{c.get('C1',{}).get('heap')} pos {c.get('C1',{}).get('pos1')}")
chk('control C2: SpaceExhaustedException, <= 4096 bytes (not 2^31), allocatedPos stays 2147483392', 'C2' in c and c['C2']['exc'] == 'SpaceExhaustedException' and c['C2']['heap'] <= 4096 and c['C2']['pos1'] == 2147483392, f"{c.get('C2',{}).get('heap')} exc {c.get('C2',{}).get('exc')}")
print('SUMMARY %d PASS, %d FAIL' % (sum(res), len(res) - sum(res)))
sys.exit(0 if all(res) else 1)
