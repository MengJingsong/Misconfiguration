#!/usr/bin/env python3
"""Derived values and B3f checks for the cluster tier of
memtable_heap_space-needsCleaning-nextClean--autonomous (as amended 2026-10-21).
Usage: python3 -I analyze.py <log root, e.g. ~/stage4-logs/ncl>"""
import re, sys, os, struct, statistics as st
MiB = 1 << 20
RUNS = [("R1", 128, None), ("R2", 512, None), ("R3", 1024, None), ("R4", 512, 0.15), ("R5", 512, 0.66)]
def f32(x): return struct.unpack('f', struct.pack('f', x))[0]
def thr(t): return f32(1.0 / 3) if t is None else f32(t)
root = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/stage4-logs/ncl")
res, checks = {}, []
def chk(name, ok, detail): checks.append((name, ok, detail)); print(("PASS " if ok else "FAIL ") + name + ": " + detail)
for R, L, t in RUNS:
    d = os.path.join(root, R)
    if not os.path.isdir(d): print(R, "missing"); continue
    tt = thr(t); T = int(f32(L * MiB * tt)); Lb = L * MiB
    trig = [l for l in open(os.path.join(d, "trig.txt")) if "keyspace1" in l]
    live = [float(re.search(r"live: ([0-9.]+)/", l).group(1)) for l in trig]
    used = [float(re.search(r"Used total: ([0-9.]+)/", l).group(1)) for l in trig]
    sysrun = open(os.path.join(d, "system-run.log")).read()
    nflush = len(re.findall(r"Enqueuing flush of keyspace1\.standard1, Reason: MEMTABLE_LIMIT", sysrun))
    other = len([l for l in sysrun.splitlines() if "Enqueuing flush of keyspace1" in l and "MEMTABLE_LIMIT" not in l])
    bm = open(os.path.join(d, "bm.txt")).read().splitlines()
    rel = [int(re.search(r"usedBefore=(\d+)", l).group(1)) for l in bm if l.startswith("NCLREL")]
    n128 = [l for l in bm if l.startswith("NCL128")]
    off = []; lv128 = []
    for l in n128:
        u, r, n = (int(re.search(k + r"=(\d+)", l).group(1)) for k in ("used", "recl", "nextClean"))
        off.append(n - r); lv128.append(u - r)
    blk = [l for l in bm if l.startswith("NCLBLK")]
    nblk = max([int(re.search(r"n=(\d+)", l).group(1)) for l in blk], default=0)
    o1 = [int(x.split()[1]) for x in open(os.path.join(d, "pool.txt")) if len(x.split()) > 1 and x.split()[1].isdigit()]
    base = [int(x.split()[3]) for x in open(os.path.join(d, "base.txt")) if "Total" in x]
    lives = [int(x.split()[3]) for x in open(os.path.join(d, "live.txt")) if "Total" in x]
    B = st.median(base); Plive = max(lives) - B; Ppool = max(rel) if rel else 0
    blocked = re.search(r"BlockedOnAllocation Count: (\d+)", open(os.path.join(d, "run.log")).read())
    blocked = int(blocked.group(1)) if blocked else -1
    exact = sum(1 for o in off if o == T)
    # informational (not a frozen check): O7 lines whose logged snapshot is self-consistent (used - recl > T,
    # i.e. no switch happened between the return and the read), and how many of those are exact
    cons = [(o, v) for o, v in zip(off, lv128) if v > T]
    print("   INFO %s O7: %d lines, %d self-consistent, %d of those exact; live-T over consistent lines: min %s max %s B" % (
        R, len(off), len(cons), sum(1 for o, v in cons if o == T), min((v - T for o, v in cons), default=None), max((v - T for o, v in cons), default=None)))
    r = dict(L=L, t=tt, T=T, ntrig=len(trig), live_med=st.median(live) if live else None, live_min=min(live, default=None),
             live_max=max(live, default=None), used_min=min(used, default=None), nflush=nflush, other=other,
             Ppool=Ppool, O1max=max(o1, default=0), nO1=len(o1), B=B, Plive=Plive, nlive=len(lives), blocked=blocked,
             n128=len(n128), exact128=exact, lv128_max_over=(max(lv128) - T) if lv128 else None,
             lv128_min_over=(min(lv128) - T) if lv128 else None, nblk_trace=nblk)
    res[R] = r
    print(R, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})
    print("   MiB: T=%.1f Ppool=%.1f O1max=%.1f B=%.1f Plive=%.1f" % (T / MiB, Ppool / MiB, r["O1max"] / MiB, B / MiB, Plive / MiB))
print()
band = {"R1": (0.30, 0.42), "R2": (0.30, 0.42), "R3": (0.30, 0.42), "R4": (0.13, 0.22), "R5": (0.64, 0.75)}
for R, r in res.items():
    lo, hi = band[R]
    chk("P1 %s median live_trig in [%s,%s]" % (R, lo, hi), r["live_med"] is not None and lo <= r["live_med"] <= hi, str(r["live_med"]))
    if R in ("R1", "R2", "R3"):
        chk("P1 %s Used total >= 0.30 at every trigger" % R, r["used_min"] is not None and r["used_min"] >= 0.30, str(r["used_min"]))
    chk("P1b %s nextClean-recl == (long)(L*t) in >=95%% of line-128 trues" % R, r["n128"] > 0 and r["exact128"] >= 0.95 * r["n128"], "%d/%d" % (r["exact128"], r["n128"]))
    chk("P2 %s P_pool <= L+8MiB" % R, r["Ppool"] <= r["L"] * MiB + 8 * MiB, "%.1f MiB" % (r["Ppool"] / MiB))
    chk("P2 %s P_pool >= t*L" % R, r["Ppool"] >= r["T"], "%.1f >= %.1f MiB" % (r["Ppool"] / MiB, r["T"] / MiB))
    chk("P2 %s O1 (live memtables) <= L" % R, r["O1max"] <= r["L"] * MiB, "%.1f MiB" % (r["O1max"] / MiB))
    if R == "R5":
        chk("P2 R5 P_pool >= 0.85 L", r["Ppool"] >= 0.85 * r["L"] * MiB, "%.1f MiB" % (r["Ppool"] / MiB))
        print("INFO R5 BlockedOnAllocation Count (expected > 0):", r["blocked"])
    else:
        print("INFO %s BlockedOnAllocation Count (expected 0 or small): %s" % (R, r["blocked"]))
    chk("P4 %s P_live <= 1.15 P_pool + 64MiB" % R, r["Plive"] <= 1.15 * r["Ppool"] + 64 * MiB, "%.1f <= %.1f MiB" % (r["Plive"] / MiB, (1.15 * r["Ppool"] + 64 * MiB) / MiB))
    chk("Attr %s no keyspace1 flush with another reason" % R, r["other"] == 0, str(r["other"]))
if "R1" in res and "R3" in res:
    q = res["R1"]["nflush"] / max(res["R3"]["nflush"], 1)
    chk("P3 N_flush(R1)/N_flush(R3) in [6,10]", 6 <= q <= 10, "%.2f (%d/%d)" % (q, res["R1"]["nflush"], res["R3"]["nflush"]))
    chk("P3 N_flush(R1) in 85..125", 85 <= res["R1"]["nflush"] <= 125, str(res["R1"]["nflush"]))
    chk("P3 N_flush(R3) in 11..16", 11 <= res["R3"]["nflush"] <= 16, str(res["R3"]["nflush"]))
    dl = (res["R3"]["Plive"] - res["R1"]["Plive"]) / MiB
    chk("P5 P_live(R3)-P_live(R1) >= 250 MiB", dl >= 250, "%.1f MiB" % dl)
if "R2" in res and "R4" in res:
    q = res["R4"]["nflush"] / max(res["R2"]["nflush"], 1)
    chk("P3 N_flush(R4)/N_flush(R2) in [1.7,2.6]", 1.7 <= q <= 2.6, "%.2f (%d/%d)" % (q, res["R4"]["nflush"], res["R2"]["nflush"]))
print("\nrefuted-if (B3f): P_pool>1.1L any run; P_live>1.15L+64MiB in R1/R2; N_flush R1/R3<3; live_trig not moving R4/R2/R5; P_live(R3)-P_live(R1)<100MiB")
for R, r in res.items():
    if r["Ppool"] > 1.1 * r["L"] * MiB: print("REFUTE-ROW P_pool > 1.1 L in", R)
    if R in ("R1", "R2") and r["Plive"] > (1.15 * r["L"] + 64) * MiB: print("REFUTE-ROW P_live > 1.15L+64 in", R)
print("summary: %d PASS, %d FAIL" % (sum(c[1] for c in checks), sum(not c[1] for c in checks)))
