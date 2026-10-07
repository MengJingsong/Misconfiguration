#!/usr/bin/env python3
"""Self-check of run 1 (results section 5): recompute the conclusion's numbers from the raw files in this folder only."""
import ast, csv, json, os, re

out = []
def say(ok, what):
    out.append(('holds     ' if ok else 'DOES NOT HOLD ') + what); print(out[-1])

u = [l.split() for l in open('unit/run.out') if l.startswith('STAGE4 check ')]
say(len(u) >= 140 and not [l for l in u if 'MISMATCH' in l], f'unit: {len(u)} checks printed, 0 MISMATCH')
say(any(l[2] == 'C2_full_ascending_completes' and l[-1] == 'ok' for l in u) and any(l[2] == 'C2_count_plus_one' and l[-1] == 'ok' for l in u) and any(l[2] == 'C3_scan_completes' and l[-1] == 'ok' for l in u), 'unit: the late-SSTable arm (completes, count +1) and the scan arm (completes) are ok')
cal = json.load(open('cluster/calibration.json'))
o = cal['o']; EST = {int(k): v for k, v in cal['est'].items()}
say(o == 88.0 and 'o 88' in open('unit/run.out').read(), f'o = {o} in the cluster calibration equals the unit tier\'s 88')
LADDER = [100, 141, 200, 283, 400, 566, 800, 1131, 1600, 2263, 3200]
VAL = {'16m': 16777216, '16k': 16384, '64k': 65536, '256k': 262144, 's64k': 65536, 's16m': 16777216, 'none': None}
R = {}
for l in VAL:
    R[l] = [r for r in csv.DictReader(open(f'cluster/{l}/readings.csv'))]
big = {}
for l, F in VAL.items():
    lad = [r for r in R[l] if r['arm'].startswith('ladder')]
    ok = True; acc = []
    for r, B in zip(lad, LADDER):
        accepted = r['outcome'] == 'OK'
        exp = F is None or EST[B] <= F
        ok &= (accepted == exp)
        if accepted:
            acc.append(B)
        else:
            ok &= ('4' in r['codes'] and r['aborts_delta'] == '1' and r['cache_entries_after'] == r['cache_entries_before'] and r['cache_size_after'] == r['cache_size_before'])
    say(ok and len(lad) == 11, f'cluster {l}: accepted partitions up to {acc[-1] if acc else None} blocks == (est <= F); every refusal has code 4, aborts +1 and an unchanged key cache')
    if F is not None and l in ('16k', '64k', '256k'):
        big[l] = EST[acc[-1]]
        say(F / 1.42 < big[l] <= F, f'cluster {l}: largest accepted est {big[l]} in (F/1.42, F] = ({F/1.42:.0f}, {F}]')
say(abs(big['64k'] / big['16k'] - 4) < 1.2 and abs(big['256k'] / big['64k'] - 4) < 1.2, f'largest accepted est ratios {big["64k"]/big["16k"]:.2f} and {big["256k"]/big["64k"]:.2f} (about 4 and 4 within the ladder step)')
def deltas(l):
    return [int(r['cache_size_after']) - int(r['cache_size_before']) for r in R[l] if r['arm'].startswith('ladder') and r['outcome'] == 'OK']
d16 = deltas('16m'); sl = [(d16[i] - d16[i-1]) / (EST[LADDER[i]] - EST[LADDER[i-1]]) for i in range(1, len(d16))]
say((max(sl) - min(sl)) / max(sl) < 0.20, f'16m: cache weight vs estimate slope {min(sl):.3f}..{max(sl):.3f} (linear within 20%)')
ds = deltas('s16m')
say(len(ds) == 11 and len(set(ds)) <= 2, f's16m (stock cache size): weight added by the 11 accepted partitions {sorted(set(ds))} (constant; the bound on heap is column_index_cache_size, not the limit)')
dn = [r for r in R['none'] if r['arm'].startswith('ladder')]
say(all(r['outcome'] == 'OK' and r['rowindexsize_count_delta'] == '0' for r in dn), 'none: all accepted, RowIndexSize count unchanged for every read')
c1 = [r for r in R['64k'] if r['arm'].startswith('C1')]
say(len(c1) == 3 and c1[0]['outcome'] == 'OK' and c1[1]['outcome'] == 'OK' and c1[1]['cache_entries_after'] == c1[1]['cache_entries_before'] and c1[1]['rowindexsize_count_delta'] == '0' and c1[2]['outcome'].startswith('ERR'), 'C1: cached read completes with no new entry and no count change; after invalidation it is refused')
c2 = [r for r in R['64k'] if r['arm'].startswith('C2')]
say(len(c2) == 3 and c2[0]['outcome'].startswith('ERR') and c2[1]['outcome'] == 'OK' and c2[2]['outcome'].startswith('ERR'), 'C2: ck>=1000 refused, full ascending completes, full descending refused')
asc = ast.literal_eval(c2[1]['command'])
say('null' in asc and 'ks1.t2' in asc, f'C2 ascending: checksize commands seen {sorted(set(asc))} (the late SSTable is read with command=null)')
c3 = [r for r in R['64k'] if r['arm'].startswith('C3')]
say(len(c3) == 1 and c3[0]['outcome'] == 'OK' and set(ast.literal_eval(c3[0]['command'])) == {'null'}, 'C3: the scan completes and every checksize line has command=null')
open('selfcheck.txt', 'w').write('\n'.join(out) + '\n')
