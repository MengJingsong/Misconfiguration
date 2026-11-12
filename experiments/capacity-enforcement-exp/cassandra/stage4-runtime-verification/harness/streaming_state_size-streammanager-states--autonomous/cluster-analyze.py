#!/usr/bin/env python3
"""Cluster-tier (B3) analysis of streaming_state_size-streammanager-states--autonomous: B3f/B3g as amended by S4-A8, S4-A9.
usage: cluster-analyze.py <run-dir>   (reads <run-dir>/unit/o53-lines.txt for w and d, <run-dir>/cluster/<label>/)"""
import csv, os, re, sys
R = sys.argv[1]
w = d = None
for line in open(f'{R}/unit/o53-lines.txt'):
    m = re.search(r'w=(\d+)', line)
    if m and 'EMPTY' in line: w = int(m.group(1))
    m = re.search(r'peer=true size=16KiB .* inserted=(\d+) retained=(\d+) .*deep=(\d+)', line)
    if m and int(m.group(1)) == 5000: d = int(m.group(3)) / int(m.group(2))
print(f"w = {w} B (unit EMPTY + TIMEUUID_SIZE); d = {d:.1f} B (unit deep per entry, 16KiB addPeer=true, final sample)")
LBL = {'s16k': 16384, 's32k': 32768, 's4m': 4 * 1048576, 's4m-nostats': 4 * 1048576}
out = []
def exp(ok, text): out.append(ok); print(f"EXPECTED: {'PASS' if ok else 'FAIL'}  {text}")
data, meta = {}, {}
for lbl, S in LBL.items():
    D = f'{R}/cluster/{lbl}'
    rows = list(csv.DictReader(open(f'{D}/samples.csv')))
    data[lbl] = {(int(r['i']), int(r['node'])): r for r in rows}
    summ = open(f'{D}/summary.txt').read()
    fails = int(re.search(r'failed: (\d+)', summ).group(1))
    sizeok = all(re.search(rf'n{k}: Storing streaming state for 3d or for size {S}$', summ, re.M) for k in (1, 2))
    meta[lbl] = dict(S=S, fails=fails, sizeok=sizeok)
    print(f"--- {lbl}: S={S} P={S // w} rebuild failures={fails} size line ok={sizeok}")
    for i in range(25, 151, 25):
        print("   i=%3d " % i + "  ".join(f"n{k}: vtable={data[lbl][(i,k)]['vtable']:>4} live={data[lbl][(i,k)]['live']:>4} "
                                          f"live_bytes={data[lbl][(i,k)]['live_bytes']:>6} heap={data[lbl][(i,k)]['heap_used_mb']}" for k in (1, 2)))
V = lambda lbl, i, k: int(data[lbl][(i, k)]['vtable']); LV = lambda lbl, i, k: int(data[lbl][(i, k)]['live'])
I = range(25, 151, 25)
print("--- validity (C1, C2)")
c1 = not all(meta[l]['fails'] == 0 and meta[l]['sizeok'] for l in LBL) or any(V('s4m', i, k) < i for i in I for k in (1, 2))
exp(all(meta[l]['fails'] == 0 for l in LBL), "no rebuild failed")
exp(all(meta[l]['sizeok'] for l in LBL), "size log line as configured on both nodes, every label")
for k in (1, 2): exp(all(V('s4m', i, k) == i for i in I), f"4MiB n{k}: count = i at every sample {[V('s4m', i, k) for i in I]}")
c2 = any(V('s4m-nostats', i, k) > 0 or LV('s4m-nostats', i, k) > 0 for i in I for k in (1, 2))
for k in (1, 2): exp(all(V('s4m-nostats', i, k) == 0 and LV('s4m-nostats', i, k) == 0 for i in I), f"stats disabled n{k}: count = live = 0")
print("--- binding values (S4-A8)")
c3 = c4 = c5_bound = False; flat_ok = True; band = []; lc2 = []
for lbl in ('s16k', 's32k'):
    S = LBL[lbl]; P = S // w
    if P >= 150: print(f"{lbl}: P={P} >= 150, not binding"); continue
    for k in (1, 2):
        a, b = V(lbl, 125, k), V(lbl, 150, k); live = LV(lbl, 150, k)
        flat = abs(b - a) <= 4; flat_ok &= flat and b <= P
        exp(flat, f"{lbl} n{k}: flat |count(150) - count(125)| = |{b} - {a}| <= 4")
        exp(b <= P, f"{lbl} n{k}: count(150) {b} <= P {P}")
        if (not flat and b > P) or b >= 135: c3 = True
        if live - b > 5 and live > P + 5: c4 = True
        exp(live * d <= 2 * S, f"{lbl} n{k}: live*d = {live}*{d:.1f} = {live*d:.0f} <= 2S = {2*S}")
        if live * d > 2 * S: c5_bound = True
        band.append(0.7 * P <= b <= P); print(f"   secondary: {lbl} n{k} in band 0.7P={0.7*P:.1f} <= {b} <= {P}: {band[-1]}")
for lbl in LBL:
    for k in (1, 2):
        for i in I:
            lc2.append(LV(lbl, i, k) - V(lbl, i, k) <= 2)
exp(all(lc2), "live - count <= 2 at every sample (secondary)")
print("--- matched B3g row (S4-A9, first match)")
if c1: row = "C1 Invalid run"
elif c2: row = "C2 Invalid instrument"
elif c3: row = "C3 Refuted - does not cap"
elif c4: row = "C4 Refuted (real resource) - does not cap"
elif flat_ok and c5_bound: row = "C5 Refuted (bound) - caps (soft)"
elif flat_ok and not c5_bound and all(LV(l, i, k) - V(l, i, k) <= 5 for l in ('s16k', 's32k') for i in [150] for k in (1, 2)): row = "C6 Confirmed - caps"
else: row = "C7 Not confirmed (no matching row)"
print("MATCHED: " + row + f"; secondary: in band {sum(band)}/{len(band)}, live-count<=2 {sum(lc2)}/{len(lc2)}")
print(f"summary: {sum(out)} PASS, {len(out)-sum(out)} FAIL")
