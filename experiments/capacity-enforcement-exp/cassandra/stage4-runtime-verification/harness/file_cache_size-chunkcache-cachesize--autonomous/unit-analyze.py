#!/usr/bin/env python3
"""Unit-tier analyzer for file_cache_size-chunkcache-cachesize--autonomous.
usage: unit-analyze.py <unit-output-dir>   (reads unit-32.txt unit-64.txt unit-128.txt unit-1024.txt unit-off.txt)
Prints the readings per run and each B2f prediction / B2g row condition as a fact (TRUE/FALSE). It matches no row itself."""
import os, sys

MiB = 1 << 20
D = sys.argv[1]
RUNS = [("U0", "32", 32), ("U1", "64", 64), ("U2", "128", 128), ("U3", "1024", 1024), ("U4", "off", 128)]
COLS = ["phase", "reads", "weighted", "entries", "misses", "poolSize", "poolOverflow", "poolUsed", "direct"]


def load(v):
    p = os.path.join(D, "unit-%s.txt" % v)
    if not os.path.exists(p):
        return None
    r = {"samples": [], "null": False, "cap": None, "other": []}
    for line in open(p):
        f = line.strip().split(",")
        if f[0] == "CACHE_NULL":
            r["null"] = True
        elif f[0] == "CAPACITY":
            r["cap"] = int(f[1])
        elif f[0] in ("SAMPLE", "FINAL"):
            d = dict(zip(COLS, f[1:]))
            for k in COLS[1:]:
                d[k] = int(d[k])
            r["samples"].append(d)
        else:
            r["other"].append(line.strip())
    return r


def fmt(b):
    return "%d (%.2f MiB)" % (b, b / MiB)


res = {}
for name, v, fcs in RUNS:
    r = load(v)
    print("== %s file_cache_size=%s" % (name, v))
    if r is None:
        print("  no output")
        continue
    res[name] = r
    s = r["samples"]
    for o in r["other"]:
        print("  " + o)
    print("  cache: %s" % ("CACHE_NULL" if r["null"] else "capacity " + fmt(r["cap"])))
    if not s:
        print("  no samples")
        continue
    fin = s[-1]
    mx = {k: max(x[k] for x in s) for k in COLS[1:]}
    r["fin"], r["mx"] = fin, mx
    print("  samples %d, reads %d" % (len(s), fin["reads"]))
    for k in ("weighted", "entries", "misses", "poolSize", "poolOverflow", "poolUsed", "direct"):
        print("  %-12s final %-26s max %s" % (k, fmt(fin[k]) if k not in ("entries", "misses") else fin[k],
                                               fmt(mx[k]) if k not in ("entries", "misses") else mx[k]))
    for ph in ("loaded", "endpass1", "endpass2"):
        x = [y for y in s if y["phase"] == ph]
        if x:
            x = x[-1]
            print("  %-9s weighted %s entries %d misses %d poolSize %s direct %s" % (ph, fmt(x["weighted"]), x["entries"], x["misses"], fmt(x["poolSize"]), fmt(x["direct"])))
    if not r["null"]:
        cap = r["cap"]
        print("  evictions (misses - entries) final: %d" % (fin["misses"] - fin["entries"]))
        first_full = next((y for y in s if y["weighted"] >= 0.95 * cap), None)
        print("  first sample with weighted >= 0.95 cap: %s" % (("reads %d (%s)" % (first_full["reads"], first_full["phase"])) if first_full else "never"))
        over = [y for y in s if y["weighted"] > cap]
        print("  samples with weighted > cap: %d; > cap+16384: %d" % (len(over), len([y for y in s if y["weighted"] > cap + 16384])))
    slabs = mx["poolSize"] - 0
    print("  pool slab bytes (poolSize - poolOverflow) max: %s; threshold %s" % (fmt(max(x["poolSize"] - x["poolOverflow"] for x in s)), fmt(fcs * MiB)))

print("\n== B2f prediction facts")
def chk(label, cond):
    print("  [%s] %s" % ("TRUE " if cond else "FALSE", label))

for name in ("U0", "U4"):
    if name in res and "fin" in res[name]:
        r = res[name]
        chk("%s prints CACHE_NULL" % name, r["null"])
        chk("%s pool max size <= 8 MiB ('a few MiB at most'); max %s" % (name, fmt(r["mx"]["poolSize"])), r["mx"]["poolSize"] <= 8 * MiB)
for name, fcs, exp_entries in (("U1", 64, 2048), ("U2", 128, 6144)):
    if name in res and "fin" in res[name]:
        r = res[name]; cap = (fcs - 32) * MiB; fin, mx = r["fin"], r["mx"]
        chk("%s capacity == %d" % (name, cap), r["cap"] == cap)
        chk("%s max weighted <= cap (%s)" % (name, fmt(mx["weighted"])), mx["weighted"] <= cap)
        chk("%s every sample <= cap + 16384" % name, all(x["weighted"] <= cap + 16384 for x in r["samples"]))
        chk("%s final weighted in [0.95 cap, cap] (%s)" % (name, fmt(fin["weighted"])), 0.95 * cap <= fin["weighted"] <= cap)
        chk("%s final entries within 5%% of %d (%d)" % (name, exp_entries, fin["entries"]), abs(fin["entries"] - exp_entries) <= 0.05 * exp_entries)
        chk("%s poolSize <= %d MiB + poolOverflow at every sample" % (name, fcs), all(x["poolSize"] <= fcs * MiB + x["poolOverflow"] for x in r["samples"]))
        chk("%s poolOverflow <= 32 MiB (max %s)" % (name, fmt(mx["poolOverflow"])), mx["poolOverflow"] <= 32 * MiB)
        chk("%s poolSize <= file_cache_size + cacheSize (B2g row 5 not met) (max %s)" % (name, fmt(mx["poolSize"])), mx["poolSize"] <= fcs * MiB + cap)
        chk("%s final weighted >= 50%% cap (B2g row 4 not met)" % name, fin["weighted"] >= 0.5 * cap)
if "U3" in res and "fin" in res["U3"]:
    r = res["U3"]; fin = r["fin"]
    e1 = [y for y in r["samples"] if y["phase"] == "endpass1"][-1]
    chk("U3 final weighted in [200, 215] MiB (%s)" % fmt(fin["weighted"]), 200 * MiB <= fin["weighted"] <= 215 * MiB)
    chk("U3 final entries ~12,900 (+-5%%) (%d)" % fin["entries"], abs(fin["entries"] - 12900) <= 0.05 * 12900)
    chk("U3 weighted same after pass 2 as after pass 1 (%s vs %s)" % (fmt(e1["weighted"]), fmt(fin["weighted"])), e1["weighted"] == fin["weighted"])
    chk("U3 far above U1/U2 caps (> 2 x 96 MiB)", fin["weighted"] > 192 * MiB)
    # linear growth during pass 1: weighted / reads roughly constant
    p1 = [y for y in r["samples"] if y["phase"] == "pass1"]
    if p1:
        a, b = p1[len(p1) // 4], p1[-1]
        print("  U3 pass-1 bytes per read at 1/4 and end: %.0f, %.0f" % (a["weighted"] / a["reads"], b["weighted"] / b["reads"]))
if all(n in res and "fin" in res[n] for n in ("U1", "U2")):
    ratio = res["U2"]["fin"]["weighted"] / max(1, res["U1"]["fin"]["weighted"])
    chk("U2/U1 final weighted ratio ~3 (within 10%%): %.3f" % ratio, abs(ratio - 3) <= 0.3)
if "U0" in res:
    chk("U0 non-null cache (B2g row 6)", not res["U0"]["null"])
