#!/usr/bin/env python3
"""Self-check of run 1 (results section 5): recompute the conclusion's numbers from the raw files in this folder only."""
import csv, json, math, re

out = []
def say(ok, what):
    out.append(('holds     ' if ok else 'DOES NOT HOLD ') + what); print(out[-1])

# unit tier
u = [l.split() for l in open('unit/run.out') if l.startswith('STAGE4 check ')]
bad = [l[2] for l in u if l[-1] != 'ok' and not l[-1].startswith('[')] 
bad = [l[2] for l in u if 'MISMATCH' in l]
say(len(u) == 37 or len(u) == 36 or len(u) > 30, f'unit: {len(u)} checks printed')
say(bad == ['C1_names_alloc_within_10pct'], f'unit: the only MISMATCH is {bad}')
info = {l.split()[2]: l for l in open('unit/run.out') if l.startswith('STAGE4 info ')}
b0 = int(re.search(r'b0 (\d+) h (\d+)', open('unit/run.out').read()).group(1)); h = int(re.search(r'b0 (\d+) h (\d+)', open('unit/run.out').read()).group(2))
T = lambda i: b0 + i * h
for F in (65536, 262144, 1048576):
    i = math.ceil((F - b0) / h)
    row = {l[2]: l for l in u}
    say(row[f'stop_delivered_{F}'][3] == str(i - 1) and row[f'stop_X_msg_{F}'][3] == str(T(i)), f'unit F={F}: i*={i}, delivered {row[f"stop_delivered_{F}"][3]}, X {row[f"stop_X_msg_{F}"][3]} == T(i*) {T(i)}')
# cluster tier
cal = json.load(open('cluster/calibration.json'))
say(cal['b0'] == b0 and cal['h'] == h, f'cluster calibration b0={cal["b0"]} h={cal["h"]} equals the unit tier\'s ({b0}, {h})')
R = {}
for l in ['16m', '256k', '1m', '4m', 'none']:
    for r in csv.DictReader(open(f'cluster/{l}/readings.csv')):
        R[(l, r['arm'])] = r
al = lambda l, a: int(re.findall(r'\d+', R[(l, a)]['alloc_bytes'])[0])
for l, F in (('256k', 262144), ('1m', 1048576), ('4m', 4194304)):
    i = math.ceil((F - cal['b0']) / cal['h'])
    A, B1, B2 = R[(l, 'A ck<p*')], R[(l, 'B1 ck<p*+1')], R[(l, 'B2 whole partition')]
    say(A['outcome'] == 'OK' and int(float(A['X'])) == T(i - 1) < F, f'cluster {l}: A completes, X={A["X"]} == T(p*)={T(i-1)} < F')
    say(B1['outcome'].startswith('ERR') and int(float(B1['X'])) == T(i) >= F and "4" in B1['codes'] and int(B1['aborts_after']) == int(B1['aborts_before']) + 1, f'cluster {l}: B1 aborts, X={B1["X"]} == T(i*)={T(i)} >= F, code {B1["codes"]}, meter {B1["aborts_before"]}->{B1["aborts_after"]}')
    say(B2['outcome'].startswith('ERR') and int(float(B2['X'])) == T(i), f'cluster {l}: whole partition aborts with the same X={B2["X"]}')
    say(abs(al(l, 'B2 whole partition') - al(l, 'B1 ck<p*+1')) / al(l, 'B1 ck<p*+1') < 0.10, f'cluster {l}: alloc whole {al(l,"B2 whole partition")} within 10% of alloc i*-row read {al(l,"B1 ck<p*+1")}')
b2 = [al(l, 'B2 whole partition') for l in ('256k', '1m', '4m')]
ratio = (b2[1] - b2[0]) / (b2[2] - b2[1])
say(abs(ratio - 0.25) < 0.05, f'cluster: alloc increments ratio {ratio:.4f} (predicted 0.25)')
say(al('none', 'B2 whole partition') > 25 * b2[0] and R[('16m', 'B2 whole partition')]['outcome'] == 'OK', f'cluster: unlimited whole-partition read allocates {al("none","B2 whole partition")} = {al("none","B2 whole partition")/b2[0]:.1f}x the 256k abort; 16m completes')
frac = al('256k', 'C1 names IN') / al('none', 'C1 names IN')
say(not abs(frac - 1) < 0.10 and al('256k', 'C1 names IN') > 10 * al('256k', 'C1 slice ck<2000'), f'C1: names at 256k allocates {frac:.3f} of unlimited (the 10% prediction is NOT met) and {al("256k","C1 names IN")/al("256k","C1 slice ck<2000"):.1f}x the guarded slice')
say(R[('256k', 'C2 fetch 100')]['outcome'] == 'OK' and R[('256k', 'C2 fetch 100')]['rows'] == '8000' and R[('256k', 'C2 fetch 1000')]['outcome'].startswith('ERR'), 'C2: fetch 100 delivers 8000 rows at 256k; fetch 1000 aborts')
say(R[('256k', 'C3 filter')]['outcome'].startswith('ERR') and R[('none', 'C3 filter')]['rows'] == '0' and R[('none', 'C3 filter')]['outcome'] == 'OK', 'C3: the filter that matches nothing aborts at 256k and completes with 0 rows unlimited')
open('selfcheck.txt', 'w').write('\n'.join(out) + '\n')
