#!/usr/bin/env python3
"""o72 unit-tier analysis: checks B2f predictions with the M4 reading rules.
Usage: analyze_unit.py <results-dir>   (holds A-readings.txt, B0/B1/B2-readings.txt, fprime.txt, A-errorlines.txt)"""
import re, sys, statistics, os
R = sys.argv[1]
MiB = 1 << 20

def kv(line):
    return {k: v for k, v in re.findall(r'(\w+)=(\S+)', line)}

out = []
def p(s=''):
    out.append(s); print(s)

# ---- Test A
lines = open(os.path.join(R, 'A-readings.txt')).read().splitlines()
A = [kv(l) for l in lines if l.startswith('O72A ')]
A4 = [kv(l) for l in lines if l.startswith('O72A4 ')]
ok_all = True
def expectA(limit, step):
    if limit == 512 * 1024:
        return (0, 0, 0)
    if limit == 7 * MiB // 2:
        n = min(step + 1, 3)
        return (n * MiB, n * MiB, n)
    if limit == 10 * MiB:
        n = min(step + 1, 10)
        return (n * MiB, n * MiB, n)
p('== Test A')
for limit in (512 * 1024, 7 * MiB // 2, 10 * MiB):
    rows = [r for r in A if int(r['limit']) == limit]
    bad = []
    for r in rows:
        e = expectA(limit, int(r['step']))
        got = (int(r['operand']), int(r['onDisk']), int(r['files']))
        if got != e:
            bad.append((r['step'], got, e))
    ok = len(rows) == 20 and not bad
    ok_all &= ok
    p(f'limit={limit}: rows={len(rows)} mismatches={bad[:5]} -> {"MATCH" if ok else "MISMATCH"}'
      f'; max operand={max(int(r["operand"]) for r in rows) if rows else None}')
p('== A4')
bad = []
for r in A4:
    s = int(r['step'])
    if s < 3:
        e = ((s + 1) * MiB, (s if s >= 1 else 0) * MiB, MiB, s + 1)
    else:
        e = (3 * MiB, 2 * MiB, MiB, 2)
    got = (int(r['operand']), int(r['onDiskOk']), int(r['onDiskRo']), int(r['tracked']))
    if got != e:
        bad.append((s, got, e))
err = open(os.path.join(R, 'A-errorlines.txt')).read().splitlines() if os.path.exists(os.path.join(R, 'A-errorlines.txt')) else []
errg00 = [l for l in err if 'g00.cq4' in l]
ok4 = len(A4) == 12 and not bad and len(errg00) == 1
p(f'A4 rows={len(A4)} mismatches={bad} ERROR lines for g00={len(errg00)} -> {"MATCH" if ok4 else "MISMATCH"}')
ok_all &= ok4
p(f'A rows matched overall: {ok_all}')

# ---- Test B
fp = int(re.search(r'Fprime=(\d+)', open(os.path.join(R, 'fprime.txt')).read()).group(1))
p(f"== Test B   F'={fp} ({fp / MiB:.3f} MiB)")
res = {}
for tag in ('B0', 'B1', 'B2'):
    L = open(os.path.join(R, f'{tag}-readings.txt')).read().splitlines()
    S = [kv(l) for l in L if l.startswith('O72B ')]
    LEN = [kv(l) for l in L if l.startswith('O72B-LEN ')]
    MX = [kv(l) for l in L if l.startswith('O72B-MAX ')]
    M = int(S[0]['limit'])
    ops = [int(s['operand']) for s in S]
    trk = [int(s['tracked']) for s in S]
    rol = [int(s['rolledOnDisk']) for s in S]
    tot = [int(s['totalOnDisk']) for s in S]
    nfiles = [int(s['files']) for s in S]
    k = M // fp
    shrink = [(l['file'], int(l['lenAtFirstSeen']), int(l['lenNow'])) for l in LEN if int(l['lenNow']) < int(l['lenAtFirstSeen'])]
    r = dict(M=M, n=len(S), maxop=max(ops), maxrol=max(rol), maxtot=max(tot), finalrol=rol[-1], finalfiles=nfiles[-1], shrink=shrink, k=k)
    p(f'-- {tag}: limit={M} ({M / fp:.2f} F\'), samples={len(S)}, maxOperand={max(ops)}, maxRolled={max(rol)}, maxTotal={max(tot)}, final rolled={rol[-1]} ({rol[-1] / fp:.2f} F\'), final files={nfiles[-1]}, LEN lines={len(LEN)}, shrink files={len(shrink)}')
    if MX: p(f'   O72B-MAX: {MX[0]}')
    decreases = sum(1 for a, b in zip(ops, ops[1:]) if b < a)
    r['decreases'] = decreases
    if tag == 'B0':
        r['grows'] = rol[-1] >= 10 * fp and decreases == 0
        r['rolled_files_end'] = max(nfiles[-1] - 1, 0)
        dl = os.path.join(R, f'{tag}-deletions.txt')
        r['deletion_lines'] = len(open(dl).read().splitlines()) if os.path.exists(dl) else 0
        p(f'   deletion lines={r["deletion_lines"]}; operand decreases={decreases}; final rolled >= 10F\': {rol[-1] >= 10 * fp}; B0 grows: {r["grows"]}; rolled files at end={r["rolled_files_end"]}')
    else:
        over_op = [i for i, o in enumerate(ops) if o > M]
        # longest run of rolled > M + F'
        run = best = 0
        for x in rol:
            run = run + 1 if x > M + fp else 0
            best = max(best, run)
        bounded = not over_op and best < 15
        # steady (D2): from first sample with tracked >= k, provided the console log has >= 1 deletion line
        dl = os.path.join(R, f'{tag}-deletions.txt')
        ndel = len(open(dl).read().splitlines()) if os.path.exists(dl) else 0
        r['deletion_lines'] = ndel
        firstk = next((i for i, t in enumerate(trk) if t >= k), None)
        start = firstk if ndel > 0 else None
        p(f'   deletion lines in console log: {ndel}')
        steady_rol = rol[start:] if start is not None else []
        steady_trk = trk[start:] if start is not None else []
        med = statistics.median(steady_rol) if steady_rol else None
        mode = statistics.mode(steady_trk) if steady_trk else None
        lo, hi = k * fp * 0.95, (k + 1) * fp * 1.05
        plateau = med is not None and lo <= med <= hi and mode == k
        r.update(bounded=bounded, plateau=plateau, med=med, mode=mode, start=start, over_op=len(over_op), longest_over=best,
                 count_over_M_plus_F=sum(1 for x in rol if x > M + fp), tot_over=sum(1 for x in tot if x > M + 2 * fp))
        p(f'   samples with operand>M: {len(over_op)}; longest run rolled>M+F\': {best} samples; samples rolled>M+F\': {r["count_over_M_plus_F"]}; samples total>M+2F\': {r["tot_over"]}')
        p(f'   steady from sample {start} ({len(steady_rol)} samples): median rolled={med} ({(med or 0) / fp:.2f} F\'), window [{lo:.0f},{hi:.0f}], mode tracked={mode} (k={k})')
        p(f'   bounded={bounded} plateau={plateau}')
    res[tag] = r
ratio = res['B2']['med'] / res['B1']['med'] if res['B1'].get('med') else None
follows = ratio is not None and 1.8 <= ratio <= 2.8
p(f'== follows the knob: B2/B1 median steady rolled = {ratio} (window [1.8, 2.8]) -> {follows}')
grows_like_b0 = [t for t in ('B1', 'B2') if res[t]['finalrol'] >= 0.5 * res['B0']['finalrol']]
p(f'B1/B2 final rolled >= 0.5 x B0 final: {grows_like_b0}')
row4 = ok_all and res['B0']['grows'] and all(res[t]['bounded'] and res[t]['plateau'] for t in ('B1', 'B2')) and follows
row5 = any(not res[t]['bounded'] for t in ('B1', 'B2')) or bool(grows_like_b0)
row6 = res['B0']['rolled_files_end'] < 5
row7 = any(res[t]['shrink'] for t in res)
p(f'ROW4 (confirmed)={row4}  ROW5 (claim wrong)={row5}  ROW6 (no rolls)={row6}  ROW7 (shrink recorded)={row7}')
open(os.path.join(R, 'unit-analysis.txt'), 'w').write('\n'.join(out) + '\n')
