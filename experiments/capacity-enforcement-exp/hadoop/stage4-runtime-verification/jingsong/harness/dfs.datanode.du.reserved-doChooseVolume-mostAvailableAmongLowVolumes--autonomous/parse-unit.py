#!/usr/bin/env python3
"""Order 27 unit tier: compare u-sequence.txt (CSV rows + policy DEBUG lines in file order) with B2f.
Usage: python3 -I parse-unit.py <u-sequence.txt>
Per tag: steps to d0/d1, failing step and message, final avail, reserved0/1 == R, invariants of B2f bullets,
and for each step the DEBUG line(s) that preceded its CSV row (policy log is emitted inside getNextVolume)."""
import sys, re
MiB = 1 << 20; B = 100 * MiB; C = {"d0": 1024 * MiB, "d1": 3072 * MiB}
PRED = {  # tag: (d0 count, d1 count, failing step, most-available in message, final avail d0, d1)
  "U-R0": (10, 30, 41, 75497472, 25165824, 75497472),
  "U-R512": (5, 25, 31, 62914560, 12582912, 62914560),
  "U-R960": (0, 21, 22, 67108864, 67108864, 12582912),
  "U-EQ": (0, 0, 1, 104857600, 104857600, 2252341248),
  "U-EQ1": (0, 21, 22, 104857599, 104857599, 50331647),
  "U-R0-f75": (10, 30, 41, None, 25165824, 75497472),
  "U-R512-f75": (5, 25, 31, None, 12582912, 62914560),
  "U-R512-bal": (5, 25, 31, None, 12582912, 62914560),
}
DET = {"U-R0", "U-R512", "U-R960", "U-EQ1"}
rows = {}; pending = []
for line in open(sys.argv[1]):
    line = line.rstrip("\n")
    if line.startswith("CSV,"):
        f = line.split(",", 11)
        if f[2] == "step":
            continue
        tag = f[1]
        r = dict(tag=tag, step=int(f[2]), R=int(f[3]), res0=int(f[4]), res1=int(f[5]), a0=int(f[6]), a1=int(f[7]),
                 rfr0=int(f[8]), rfr1=int(f[9]), mostLow=int(f[10]), chosen=f[11], logs=pending)
        rows.setdefault(tag, []).append(r); pending = []
    else:
        pending.append(line)
ok_all = True
for tag, P in PRED.items():
    rs = rows.get(tag, [])
    R = rs[0]["R"] if rs else None
    n0 = sum(r["chosen"] == "d0" for r in rs); n1 = sum(r["chosen"] == "d1" for r in rs)
    exc = [r for r in rs if r["chosen"].startswith("EXC")]
    fs = exc[0]["step"] if exc else None
    msg = exc[0]["chosen"] if exc else "(none)"
    m = re.search(r"\(=(\d+) B\)", msg); most = int(m.group(1)) if m else None
    last = rs[-1] if rs else None
    fa0, fa1 = (last["a0"], last["a1"]) if last else (None, None)
    resok = all(r["res0"] == R and r["res1"] == R for r in rs)
    # invariants
    over = [r for r in rs if r["chosen"] in ("d0", "d1") and (r["a0"] if r["chosen"] == "d0" else r["a1"]) <= B]
    inv = all(r["rfr0"] <= C["d0"] - R and r["rfr1"] <= C["d1"] - R for r in rs)
    nB = all(n * B <= C[v] - R < (n + 1) * B for v, n in (("d0", n0), ("d1", n1))) if tag != "U-EQ" else None
    hi = [r for r in rs if r["chosen"] == "d1"]; lo = [r for r in rs if r["chosen"] == "d0"]
    route_hi_bad = [r["step"] for r in hi if not (r["mostLow"] < B)] if tag in DET else []
    route_lo_bad = [r["step"] for r in lo if not (r["mostLow"] >= B)] if tag in DET else []
    dbg_hi_missing = [r["step"] for r in hi if not any("from high available space" in l for l in r["logs"])] if tag in DET else []
    dbg_imb = sum(any("Volumes are imbalanced" in l for l in r["logs"]) for r in rs)
    dbg_bal = sum(any("All volumes are within" in l for l in r["logs"]) for r in rs)
    order = "".join("0" if r["chosen"] == "d0" else "1" if r["chosen"] == "d1" else "X" for r in rs)
    match = (n0, n1, fs) == P[:3] and (P[3] is None or most == P[3]) and (fa0, fa1) == (P[4], P[5]) and resok
    ok_all &= match
    print(f"{tag}: R={R} d0={n0} d1={n1} fail_step={fs} most={most} final_avail={fa0}/{fa1} reservedOK={resok} "
          f"| pred d0={P[0]} d1={P[1]} fail={P[2]} most={P[3]} final={P[4]}/{P[5]} -> {'MATCH' if match else 'MISMATCH'}")
    print(f"   chosen-with-avail<=B={len(over)} rfr<=C-R={inv} nB-bracket={nB} hi-route mostLow>=B steps={route_hi_bad} "
          f"lo-route mostLow<B steps={route_lo_bad} hi-steps-without-'from high'-DEBUG={dbg_hi_missing} "
          f"steps-with-imbalanced-DEBUG={dbg_imb} steps-with-balanced-DEBUG={dbg_bal}")
    print(f"   order={order}")
    print(f"   exception: {msg}")
print("ALL TAGS MATCH B2f" if ok_all else "SOME TAG DIFFERS FROM B2f")
