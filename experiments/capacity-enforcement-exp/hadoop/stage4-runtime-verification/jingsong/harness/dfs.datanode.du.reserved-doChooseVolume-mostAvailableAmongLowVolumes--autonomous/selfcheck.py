#!/usr/bin/env python3
"""Order 27 cluster tier: compare readings-K1/K2/K3.csv and readings-K1c-<n>.csv with B3f (frozen, amended D1-5).
Usage: python3 -I selfcheck.py <dir holding the readings CSVs>
Prints, per run, the put routing (from the DataNode DEBUG lines recorded after each put), accepted puts, final
blk bytes per volume against B3f's products and budgets, and the K1c overshoot per volume."""
import csv, os, sys
D = sys.argv[1]
B = 104857600; M = 819207; S = B + M; MiB = 1 << 20; GiB = 1 << 30
PRED = {  # run: (b0, b1, d0 put range, d1 put range, first failing put, imbalanced expected)
    "K1": (GiB, 3 * GiB, range(1, 11), range(11, 41), 41, True),
    "K2": (536870912, 2147483648, range(1, 6), range(6, 26), 26, True),
    "K3": (GiB, GiB, None, None, 21, False),
}
def rows(name):
    p = os.path.join(D, name)
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []
seq = {}
for run, (b0, b1, r0, r1, fail, imb) in PRED.items():
    rs = rows(f"readings-{run}.csv")
    if not rs:
        print(f"{run}: no readings"); continue
    ok = [int(r["i"]) for r in rs if r["rc"] == "0"]
    bad = [int(r["i"]) for r in rs if r["rc"] != "0"]
    route = {int(r["i"]): r["dnDebug"].strip(";") for r in rs}
    to0 = [i for i, v in route.items() if v.startswith("d0") or v.startswith("balanced:d0")]
    to1 = [i for i, v in route.items() if v.startswith("d1") or v.startswith("balanced:d1")]
    last = rs[-1]
    blk0, blk1 = int(last["blk0"]), int(last["blk1"])
    maxblk0 = max(int(r["blk0"]) for r in rs); maxblk1 = max(int(r["blk1"]) for r in rs)
    nimb = sum(("high" in v or "low" in v) for v in route.values())
    nbal = sum(v.startswith("balanced") for v in route.values())
    nnref = sum(int(r["nnRefusals"]) for r in rs); oos = sum(int(r["dnOutOfSpace"]) for r in rs)
    # put 11 rule (K1): any put routed to d0 while the pre-put freeSpace(d0) < B
    viol = []
    for k in range(1, len(rs)):
        prev, cur = rs[k - 1], rs[k]
        v = route[int(cur["i"])]
        if v.startswith("d0") and int(prev["free0"]) < B: viol.append(int(cur["i"]))
        if v.startswith("d1") and int(prev["free1"]) < B: viol.append(int(cur["i"]))
    seq[run] = (blk0, blk1)
    print(f"{run}: accepted={len(ok)} (puts {min(ok) if ok else '-'}..{max(ok) if ok else '-'}), failed puts={len(bad)} first failed={min(bad) if bad else None} (pred {fail})")
    if r0 is not None:
        print(f"   routed d0={to0} (pred {list(r0)})")
        print(f"   routed d1 count={len(to1)} first={min(to1) if to1 else None} last={max(to1) if to1 else None} (pred {r1.start}..{r1.stop - 1}); routes={sorted(set(v for v in route.values() if v))}")
    else:
        print(f"   balanced routes: d0={len(to0)} d1={len(to1)} sequence={''.join('0' if route[i].startswith('balanced:d0') else '1' if route[i].startswith('balanced:d1') else '.' for i in sorted(route))}")
    n0p = len(r0) if r0 else 10; n1p = len(r1) if r1 else 10
    print(f"   final blk0={blk0} (pred {n0p}*S={n0p * S}; b0={b0}; <= b0: {blk0 <= b0}; max seen {maxblk0}) "
          f"blk1={blk1} (pred {n1p}*S={n1p * S}; b1={b1}; <= b1: {blk1 <= b1}; max seen {maxblk1})")
    print(f"   final free0={last['free0']} free1={last['free1']} (b0-n0*S={b0 - n0p * S}, b1-n1*S={b1 - n1p * S}); cnt={last['cnt0']}/{last['cnt1']}")
    print(f"   DEBUG imbalanced lines={nimb} balanced={nbal} (imbalanced expected: {imb}); NN refusal DEBUG lines={nnref}; DN 'Out of space'={oos}; put-to-volume-with-free<B={viol}")
    print(f"   over b+M in a sequential run: d0 {blk0 > b0 + M} d1 {blk1 > b1 + M}")
if "K1" in seq and "K2" in seq:
    print(f"K1/K2 d0 ratio = {seq['K1'][0] / seq['K2'][0]:.4f} (pred ~2: 10*S / 5*S); d1 ratio = {seq['K1'][1] / seq['K2'][1]:.4f} (30/20)")
for rep in (1, 2, 3):
    rs = rows(f"readings-K1c-{rep}.csv")
    if not rs:
        continue
    fin = rs[-1]
    b0, b1 = int(fin["blk0"]), int(fin["blk1"])
    mx0 = max(int(r["blk0"]) for r in rs); mx1 = max(int(r["blk1"]) for r in rs)
    o0, o1 = max(0, b0 - GiB), max(0, b1 - 3 * GiB)
    print(f"K1c-{rep}: final blk0={b0} blk1={b1} overshoot0={o0} ({o0 / S:.2f} S) overshoot1={o1} ({o1 / S:.2f} S) "
          f"max during: {mx0}/{mx1}; finalized {fin['fin0']}/{fin['fin1']}; samples={len(rs)}")
