#!/usr/bin/env python3
"""Unit tier (B2f/B2g) of case o32. Usage: unit-analyze.py <unit-o32.txt>
Operationalisation fixed before run 1 (results section 4): for L = 1 GiB, 'peakPending ~ total written (>= 30 MB)'
is peakPending >= 30,000,000, and 'maxQueued >> 280' is maxQueued >= 560 (2 x 280)."""
import re, sys
rows = []
for line in open(sys.argv[1]):
    if line.startswith("O32 LIMIT="):
        rows.append({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", line)})
GIB = 1073741824
ok_all = True
fin, ctl = [r for r in rows if r["LIMIT"] < GIB], [r for r in rows if r["LIMIT"] == GIB]
def exp(name, cond, detail):
    global ok_all
    ok_all &= bool(cond)
    print(f"EXPECTED: {name}: {'PASS' if cond else 'FAIL'} ({detail})")
for r in rows:
    exp(f"L={r['LIMIT']} calls=1000", r["calls"] == 1000, f"calls={r['calls']} callsOther={r['callsOther']} maxOther={r['maxOther']}")
over = []
for r in fin:
    L, s, p, q = r["LIMIT"], r["s"], r["peakPending"], r["maxQueued"]
    exp(f"L={L} L-s < peakPending <= L+s", L - s < p <= L + s, f"L-s={L-s} peak={p} L+s={L+s} peak-L={p-L} s={s}")
    exp(f"L={L} maxQueued <= floor(L/s)+1", q <= L // s + 1, f"maxQueued={q} bound={L//s+1}")
    if p > L + s: over.append(L)
for r in ctl:
    exp("L=1GiB peakPending >= 30 MB", r["peakPending"] >= 30_000_000, f"peak={r['peakPending']}")
    exp("L=1GiB maxQueued >= 560", r["maxQueued"] >= 560, f"maxQueued={r['maxQueued']}")
small = all(r["peakPending"] < r["LIMIT"] / 2 for r in fin) and all(r["peakPending"] < 30_000_000 for r in ctl)
print(f"rows: finite={len(fin)} control={len(ctl)}")
if any(r["calls"] != 1000 for r in rows): print("MATCHED: B2g row 4 (calls != 1000): result void")
elif over: print(f"MATCHED: B2g row 2 (peakPending > L + s for L in {over}): claim wrong")
elif small: print("MATCHED: B2g row 3 (limit never reached): not confirmed")
elif ok_all and len(fin) == 3 and len(ctl) == 1: print("MATCHED: B2g row 1 (claim confirmed at unit level)")
else: print("MATCHED: none -> Not confirmed (no matching row)")
