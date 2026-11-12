#!/usr/bin/env python3
"""Cluster-tier analyzer for file_cache_size-chunkcache-cachesize--autonomous.
usage: cluster-analyze.py <cluster-output-dir>
Reads C{0..3}-jmx.csv (10 s samples), C*-jmx-snap.csv (baseline/after-read1/after-read2/final), C*-snap.txt (cqlsh, NMT), C*-proc.csv.
Prints readings and each B3f prediction / B3g condition as a fact (TRUE/FALSE). It matches no row itself."""
import os, re, sys

MiB = 1 << 20
O = sys.argv[1]
COLS = ["ms", "cacheCap", "cacheSize", "entries", "misses", "poolCap", "poolSize", "poolOverflow", "poolUsed", "direct", "directCount"]
RUNS = [("C0", None, 128), ("C1", 96, 128), ("C2", 224, 256), ("C3", 992, 1024)]


def rd(p):
    rows = []
    if not os.path.exists(p):
        return rows
    for line in open(p):
        f = line.strip().split(",")
        if len(f) < len(COLS):
            continue
        d = {k: int(v) for k, v in zip(COLS, f[:len(COLS)])}
        d["tag"] = f[len(COLS)] if len(f) > len(COLS) else ""
        rows.append(d)
    return rows


def m(b):
    return "%.2f MiB" % (b / MiB) if b >= 0 else str(b)


R = {}
for name, cap, fcs in RUNS:
    s = rd(os.path.join(O, name + "-jmx.csv"))
    snaps = {d["tag"]: d for d in rd(os.path.join(O, name + "-jmx-snap.csv"))}
    if not s and not snaps:
        print("== %s: no data" % name)
        continue
    allr = s + list(snaps.values())
    mx = {k: max(x[k] for x in allr) for k in COLS[1:]}
    R[name] = dict(s=s, snaps=snaps, mx=mx, cap=cap, fcs=fcs)
    print("== %s (cacheSize %s, file_cache_size %d MiB): %d samples" % (name, m(cap * MiB) if cap else "none", fcs, len(s)))
    for t in ("baseline", "after-read1", "after-read2", "final"):
        if t in snaps:
            x = snaps[t]
            print("  %-12s cache %s entries %d misses %d | pool size %s overflow %s used %s | direct %s (n=%d)" % (
                t, m(x["cacheSize"]), x["entries"], x["misses"], m(x["poolSize"]), m(x["poolOverflow"]), m(x["poolUsed"]), m(x["direct"]), x["directCount"]))
    print("  max          cache %s entries %d | pool size %s overflow %s used %s | direct %s" % (
        m(mx["cacheSize"]), mx["entries"], m(mx["poolSize"]), m(mx["poolOverflow"]), m(mx["poolUsed"]), m(mx["direct"])))
    if cap and s:
        c = cap * MiB
        print("  samples cache > cap: %d; > cap + 32x16KiB: %d" % (sum(1 for x in allr if x["cacheSize"] > c), sum(1 for x in allr if x["cacheSize"] > c + 32 * 16384)))
        if "final" in snaps:
            f = snaps["final"]
            print("  evictions (misses - entries) at final: %d" % (f["misses"] - f["entries"]))
    snp = os.path.join(O, name + "-snap.txt")
    if os.path.exists(snp):
        txt = open(snp).read()
        for blk in txt.split("### ")[1:]:
            tag = blk.split()[0]
            ch = re.search(r"^\s*chunks\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)", blk, re.M)
            oth = re.search(r"Other \(reserved=(\d+)KB, committed=(\d+)KB\)", blk)
            rss = re.search(r"rss_kb (\d+)", blk)
            ra = re.search(r"RssAnon:\s*(\d+)", blk)
            print("  cqlsh/NMT %-12s chunks row %s | NMT Other committed %s | RSS %s | RssAnon %s" % (
                tag, ("cap %s size %s entries %s" % (m(int(ch.group(1))), m(int(ch.group(2))), ch.group(3))) if ch else "ABSENT",
                m(int(oth.group(2)) * 1024) if oth else "?", m(int(rss.group(1)) * 1024) if rss else "?", m(int(ra.group(1)) * 1024) if ra else "?"))
            R[name].setdefault("nmt", {})[tag] = int(oth.group(2)) * 1024 if oth else None
            R[name].setdefault("chunks", {})[tag] = ch is not None

print("\n== B3f prediction facts")


def chk(label, cond):
    print("  [%s] %s" % ("TRUE " if cond else "FALSE", label))


def final(n, k):
    return R[n]["snaps"]["final"][k]


if "C0" in R:
    chk("C0 no chunks row in system_views.caches (all snapshots)", not any(R["C0"].get("chunks", {}).values()))
    chk("C0 chunk-cache pool Size max <= 8 MiB ('a few MiB') (%s)" % m(R["C0"]["mx"]["poolSize"]), R["C0"]["mx"]["poolSize"] <= 8 * MiB)
for n, exp_e in (("C1", 6144), ("C2", 14336)):
    if n in R and "final" in R[n]["snaps"]:
        r = R[n]; c = r["cap"] * MiB; f = r["snaps"]["final"]
        chk("%s final size in [0.95 cap, cap] (%s)" % (n, m(f["cacheSize"])), 0.95 * c <= f["cacheSize"] <= c)
        chk("%s max size <= cap + 32 x 16 KiB (%s)" % (n, m(r["mx"]["cacheSize"])), r["mx"]["cacheSize"] <= c + 32 * 16384)
        chk("%s final entries within 5%% of %d (%d)" % (n, exp_e, f["entries"]), abs(f["entries"] - exp_e) <= 0.05 * exp_e)
        chk("%s pool Size <= %d MiB + OverflowSize at every sample" % (n, r["fcs"]), all(x["poolSize"] <= r["fcs"] * MiB + x["poolOverflow"] for x in r["s"] + list(r["snaps"].values())))
        if "C0" in R and "final" in R["C0"]["snaps"]:
            dd = f["direct"] - final("C0", "direct")
            chk("%s direct delta vs C0 (final) <= %d MiB + OverflowSize + 8 MiB (%s)" % (n, r["fcs"], m(dd)), dd <= r["fcs"] * MiB + f["poolOverflow"] + 8 * MiB)
        chk("%s final size >= 50%% cap (B3g row 6 not met)" % n, f["cacheSize"] >= 0.5 * c)
        chk("%s OverflowSize max < 0.5 x cacheSize (B3g row 4 not met) (%s)" % (n, m(r["mx"]["poolOverflow"])), r["mx"]["poolOverflow"] < 0.5 * c)
if "C3" in R and "final" in R["C3"]["snaps"]:
    f = R["C3"]["snaps"]["final"]
    chk("C3 final size in [550, 600] MiB (%s)" % m(f["cacheSize"]), 550 * MiB <= f["cacheSize"] <= 600 * MiB)
    chk("C3 final size < 992 MiB", f["cacheSize"] < 992 * MiB)
    a1 = R["C3"]["snaps"].get("after-read1")
    if a1:
        print("  C3 size after read1 %s, after read2 %s" % (m(a1["cacheSize"]), m(R["C3"]["snaps"]["after-read2"]["cacheSize"])))
    if "C0" in R and "final" in R["C0"]["snaps"]:
        dd = f["direct"] - final("C0", "direct")
        chk("C3 direct delta vs C0 ~ size (within 15%%): delta %s, size %s" % (m(dd), m(f["cacheSize"])), abs(dd - f["cacheSize"]) <= 0.15 * f["cacheSize"])
if all(n in R and "final" in R[n]["snaps"] for n in ("C0", "C1", "C2", "C3")):
    d = {n: final(n, "direct") - final("C0", "direct") for n in ("C1", "C2", "C3")}
    print("  direct deltas vs C0 (final): " + ", ".join("%s %s" % (k, m(v)) for k, v in d.items()))
    chk("ordering C0 < C1 < C2 < C3 (direct, final)", 0 < d["C1"] < d["C2"] < d["C3"])
    chk("C2 - C1 delta ~ 128 MiB +- 32 MiB (%s)" % m(d["C2"] - d["C1"]), abs(d["C2"] - d["C1"] - 128 * MiB) <= 32 * MiB)
    nm = {n: R[n].get("nmt", {}).get("final") for n in ("C0", "C1", "C2", "C3")}
    if all(v is not None for v in nm.values()):
        print("  NMT Other committed deltas vs C0 (final): " + ", ".join("%s %s" % (n, m(nm[n] - nm["C0"])) for n in ("C1", "C2", "C3")))
