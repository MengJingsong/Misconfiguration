#!/usr/bin/env python3
"""B2f/B2g (+ amendment R2) checks for the unit tier. usage: unit-analyze.py <unit log dir>"""
import re, sys, os
D = sys.argv[1]
def parse(p):
    r = {'A': [], 'B': [], 'C': None, 'setup': None}
    for l in open(p):
        l = l.strip()
        m = re.match(r'PROBE setup sFull=(\d+) s=(\d+) mPred=(\d+) F=(\d+) d=(\d+)', l)
        if m: r['setup'] = dict(zip(['sFull', 's', 'mPred', 'F', 'd'], map(int, m.groups()))); continue
        m = re.match(r'PROBE A P=(-?\d+) T=(\d+) kept=(\d+) kPred=(-?\d+) Tpred=(-?\d+) T<=P=(\w+) levels=(\S*)', l)
        if m: r['A'].append(dict(P=int(m[1]), T=int(m[2]), kept=int(m[3]), kPred=int(m[4]), Tpred=int(m[5]), lv=m[7])); continue
        m = re.match(r'PROBE B P=(\d+) T=(\d+) slackBound=(\d+) T<=P=(\w+) levels=(\S*)', l)
        if m: r['B'].append(dict(P=int(m[1]), T=int(m[2]), bound=int(m[3]), lv=m[5])); continue
        m = re.match(r'PROBE C floor P=(\d+) T=(\d+) levels=(\S*)', l)
        if m: r['C'] = dict(P=int(m[1]), T=int(m[2]), lv=m[3])
    return r
ok = {}
def E(name, cond, detail):
    ok[name] = bool(cond); print(f"EXPECTED: {name}: {'HIT' if cond else 'MISS'} -- {detail}")
reps = {}
for rep in ('rep1', 'rep2'):
    p = os.path.join(D, rep + '.probe')
    if os.path.exists(p): reps[rep] = parse(p)
if 'rep1' not in reps or reps['rep1']['setup'] is None:
    print("EXPECTED: probe output present: MISS"); sys.exit(1)
r = reps['rep1']; st = r['setup']; F, d, s, sF = st['F'], st['d'], st['s'], st['sFull']
E('B2f setup arithmetic ( s=5120 m=160 F=1280 d=4960 S_full=40960)', (s, st['mPred'], F, d, sF) == (5120, 160, 1280, 4960, 40960), str(st))
E('scenario A has 11 rows', len(r['A']) == 11, str(len(r['A'])))
row1 = row4 = row5only = True; refuted = False
for a in r['A']:
    P, T, k = a['P'], a['T'], a['kept']
    kP = 0 if P <= F else min(8, (P - F) // d)
    exact = (k == kP and T == F + kP * d)
    print(f"  A P={P} T={T} kept={k} kPred={kP} Tpred={F + kP*d} exact={exact} T<=P={T <= P} levels={a['lv']}")
    if P >= F:
        if T > P: refuted = True
        if not exact:
            row1 = False
            if abs(k - kP) != 1: row5only = False
    else:
        if T != F: row4 = False
E('B2g row 1: every A row with P >= F has kept=kPred, T=F+kPred*d, T<=P', row1 and not refuted, '')
E('B2g row 4: T = F (> P) for every P < F', row4, '')
E('B2g row 2 (claim wrong): no A row with P >= F has T > P', not refuted, '')
bok = all(F <= b['T'] <= b['bound'] for b in r['B']); bmono = len(r['B']) >= 3 and r['B'][0]['T'] > r['B'][1]['T'] > r['B'][2]['T']
for b in r['B']: print(f"  B P={b['P']} T={b['T']} bound={b['bound']} F<=T<=bound={F <= b['T'] <= b['bound']} T<=P={b['T'] <= b['P']} levels={b['lv']}")
E('B2g row 2 (claim wrong): scenario B within F <= T <= P + s/4 + F', bok and len(r['B']) == 4, '')
E('B2f B: T strictly decreasing S_full/2 -> S_full/8 (sub-prediction, R2)', bmono, str([b['T'] for b in r['B'][:3]]))
Ts = [a['T'] for a in r['A'] if a['P'] >= F]
E('B2g row 3 (claim wrong): T not unchanged from 2*S_full down to F', len(set(Ts)) > 1, str(sorted(set(Ts))))
pc = [a for a in r['A'] if a['P'] == 2 * sF]
E('B2g row 6 (positive control): T = S_full at P = 2*S_full', pc and pc[0]['T'] == sF, str(pc[0]['T'] if pc else None))
c = r['C']
E('B2g row 7 / B2h control C: T = S_full and all levels 128', c and c['T'] == sF and set(c['lv'].strip(',').split(',')) == {'128'}, str(c))
if 'rep2' in reps:
    q = reps['rep2']
    same = (q['setup'] == r['setup'] and [(a['P'], a['T'], a['kept'], a['lv']) for a in q['A']] == [(a['P'], a['T'], a['kept'], a['lv']) for a in r['A']]
            and [(b['P'], b['T'], b['lv']) for b in q['B']] == [(b['P'], b['T'], b['lv']) for b in r['B']] and q['C'] == r['C'])
    E('R2: repeat run identical', same, '')
else:
    E('R2: repeat run identical', False, 'rep2 missing')
conf = all(ok.get(k) for k in ok if not k.startswith('B2f'))
print(f"UNIT VERDICT (R2 mapping): {'Confirmed' if conf else ('Refuted' if (refuted or not ok.get('B2g row 3 (claim wrong): T not unchanged from 2*S_full down to F', True)) else 'see rows')}")
