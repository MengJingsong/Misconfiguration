#!/usr/bin/env python3
"""B2f/B2g (+ R3) of index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous: reads rep1.probe / rep2.probe,
prints EXPECTED: lines and the R3 verdict mapping. usage: unit-analyze.py <unit dir>"""
import re, sys
D = sys.argv[1]

def parse(p):
    rows = {}
    try:
        txt = open(p).read()
    except FileNotFoundError:
        return None, ''
    for l in txt.splitlines():
        m = re.match(r'PROBE (\S+) ?(.*)', l)
        if m:
            rows[m[1]] = dict(kv.split('=', 1) for kv in m[2].split() if '=' in kv)
    return rows, txt

r1, t1 = parse(f'{D}/rep1.probe'); r2, t2 = parse(f'{D}/rep2.probe')
ok = {}
def exp(name, cond, detail):
    ok[name] = bool(cond); print(f'EXPECTED: {name}: {"PASS" if cond else "FAIL"} -- {detail}')

if not r1 or 'done' not in r1:
    print('VERDICT: Invalid (rep1 incomplete)'); sys.exit(0)
s = r1['setup']; N = int(s['N']); S = int(s['S']); Fp = int(s['Fp'])
fl = r1['floor']; F = int(fl['F'])
print(f'setup: N={N} S={S} Fp={Fp} F={F} S-Fp={S-Fp} N*F={N*F}')
exp('floor operand', int(fl['R_refl']) == int(fl['R_compl']) == -N * Fp, f"R_refl={fl['R_refl']} R_compl={fl['R_compl']} pred={-N*Fp}")
b2f_k = {'P0': 0, 'P1': 0, 'P2': 3, 'P3': 7, 'P4': 10}
readers_agree = True; exact = True; prev_k = -1; mono = True
for i in range(5):
    r = r1[f'P{i}']; P = int(r['P']); R = int(r['R_refl']); Rc = int(r['R_compl']); k = int(r['k']); T = int(r['T'])
    readers_agree &= (R == Rc)
    exact &= (R == int(r['Rpred']) and k == int(r['kPred']) and T == int(r['Tpred']))
    print(f'P{i}: P={P} R={R} (compl {Rc}, pred {r["Rpred"]}) branch={R>0} k={k} (kPred {r["kPred"]}, B2f {b2f_k[f"P{i}"]}) T={T} (Tpred {r["Tpred"]}) T<=P={T<=P} tBefore={r["tBefore"]}')
    exp(f'P{i} reset full', int(r['tBefore']) == N * S, f"tBefore={r['tBefore']} N*S={N*S}")
    exp(f'P{i} k = B2f table (+-1)', abs(k - b2f_k[f'P{i}']) <= 1, f'k={k} table={b2f_k[f"P{i}"]}')
    if i == 0:
        exp('P0 row 4: R<0, branch not taken, k=0, T=N*F>P0', R < 0 and k == 0 and T == N * F and T > P, f'R={R} k={k} T={T} P0={P}')
    else:
        exp(f'P{i} row 1: R>0 and T<=P', R > 0 and T <= P, f'R={R} T={T} P={P}')
        mono &= k >= prev_k
    prev_k = k if i > 0 else prev_k
exp('readers agree (R3)', readers_agree, 'reflection vs pool - completed, all P')
exp('operand exact R=P-N*Fp, k, T formula (R3)', exact, '')
exp('k increases P1<=P2<P3<P4', mono and int(r1['P2']['k']) < int(r1['P3']['k']) < int(r1['P4']['k']), '')
exp('row 3 ruled out: k>0 at P2,P3 with R>0', int(r1['P2']['k']) > 0 and int(r1['P3']['k']) > 0, '')
pc = int(r1['P4']['T']) - int(r1['P1']['T'])
exp('positive control P4-P1 ~ N(S-F)', abs(pc - N * (S - F)) <= N * 64, f'diff={pc} N(S-F)={N*(S-F)}')
exp('ablation: P1 k=0, P2 k=3', int(r1['P1']['k']) == 0 and int(r1['P2']['k']) == 3, '')
same = r2 is not None and t2 == t1
exp('repeat rep2 == rep1', same, '')
row2 = any(int(r1[f'P{i}']['T']) > int(r1[f'P{i}']['P']) for i in range(1, 5))
row3 = int(r1['P2']['k']) == 0 or int(r1['P3']['k']) == 0
if not readers_agree:
    v = 'Invalid (operand readers disagree)'
elif row2 or row3:
    v = 'Refuted (row %s)' % ('2' if row2 else '3')
elif all(ok.values()):
    v = 'Confirmed -- Effect: caps'
else:
    v = 'Not confirmed (failed: %s)' % ', '.join(k for k, x in ok.items() if not x)
print('VERDICT:', v)
