#!/usr/bin/env python3
"""Self-check (results §5) for dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous: recompute every reading the
conclusion uses from the raw files in run1/ (not from results.md) and test it against the frozen B2f/B3f (+S2/S3/S6).
Usage: selfcheck.py <run1-dir>"""
import csv
import os
import re
import sys

R = sys.argv[1]
B = 33554432
ok_all = True


def chk(name, cond, detail):
    global ok_all
    ok_all &= bool(cond)
    print("%-4s %-58s %s" % ("OK" if cond else "FAIL", name, detail))


# ---------------- unit
rows = {}
for line in open(os.path.join(R, "unit", "pmchk.csv")):
    f = line.strip().split(",")
    if f[1] == "u3" and f[2] == "b" and f[3] == "line":
        continue
    key = ",".join(f[1:3])
    kv = dict(x.split("=", 1) for x in f[3:] if "=" in x)
    m = kv.get("M")
    rows[(key, m)] = kv
for M in (32768, 65536, 131072):
    k = str(M)
    full = rows[("u1,full", k)]
    n = M // 4096
    chk("U1 M=%d reserves" % M, rows[("u1,reserves", k)]["r"].split(";") ==
        [str(4096 * i) for i in range(1, n + 1)] + ["-1"] * 4, "ok=%s fail=%s" % (full["ok"], full["fail"]))
    chk("U1 M=%d used/max/map/warns" % M, full["used"] == k and full["maxUsed"] == k and full["mapSize"] == str(n)
        and full["noSpaceWarns"] == "4", str(full))
    rel = rows[("u1,release", k)]
    chk("U1 M=%d release+next" % M, rel["usedAfterRelease"] == str(M - 4096) and rel["nextReserve"] == k, str(rel))
    rf = rows[("u1,reflect", k)]
    chk("U1 M=%d reflective :77" % M, rf["reserve1"] == "-1" and rf["usedAfter"] == k and rf["reserve0"] == k, str(rf))
u2o = [dict(x.split("=", 1) for x in l.strip().split(",")[3:]) for l in open(os.path.join(R, "unit", "pmchk.csv"))
       if l.startswith("PMCHK,u2,one")][0]
u2t = [dict(x.split("=", 1) for x in l.strip().split(",")[3:]) for l in open(os.path.join(R, "unit", "pmchk.csv"))
       if l.startswith("PMCHK,u2,two")][0]
chk("U2 one dir: |cap-usable| <= 1 MiB", abs(int(u2o["capacity"]) - int(u2o["usable"])) <= 1048576, str(u2o))
chk("U2 two dirs: |cap-2*usable| <= 2 MiB, same store",
    abs(int(u2t["capacity"]) - 2 * int(u2t["usable"])) <= 2097152 and u2t["sameStore"] == "true", str(u2t))
u3 = {}
for l in open(os.path.join(R, "unit", "pmchk.csv")):
    f = l.strip().split(",")
    if f[1] == "u3" and f[3] != "line" and not f[3].startswith("line"):
        kv = dict(x.split("=", 1) for x in f[3:] if "=" in x)
        u3[(f[2], kv["M"])] = kv
for M, nf1 in ((32768, 8), (65536, 16)):
    k = str(M)
    i, f1, a, b, mx = (u3[(s, k)] for s in ("instr", "f1", "a", "b", "max"))
    chk("U3 M=%d loader pure-Java, cap=M" % M, i["loader"].endswith(".PmemMappableBlockLoader")
        and i["nativeAvailable"] == "false" and i["dnCacheCapacity"] == k, i["loader"])
    chk("U3 M=%d f1: %d cached, used=disk=M" % (M, nf1), f1["numBlocksCached"] == str(nf1) and f1["cacheUsed"] == k
        and f1["diskBytes"] == k and f1["couldNotReserve"] == "0", str({x: f1[x] for x in ("numBlocksCached", "cacheUsed", "diskBytes")}))
    chk("U3 M=%d (a): unchanged, NN rejects > 0, no f2 file" % M, a["numBlocksCached"] == str(nf1) and a["cacheUsed"] == k
        and a["f2FilesOnDisk"] == "0" and int(a["nnRejectDelta"]) > 0 and a["nnAddedDelta"] == "0", "rejΔ=" + a["nnRejectDelta"])
    chk("U3 M=%d (b): 4 refusals for f2, 4 WARNs, used=disk=M" % M, b["couldNotReserveF2"] == "4" and b["noSpaceWarnsNew"] == "4"
        and int(b["failedDelta"]) >= 4 and b["cacheUsed"] == k and b["diskBytes"] == k and b["f2FilesOnDisk"] == "0",
        "failedΔ=" + b["failedDelta"])
    chk("U3 M=%d max used/disk <= M" % M, int(mx["maxCacheUsed"]) <= M and int(mx["maxDiskBytes"]) <= M, str(mx))
k = "131072"
a, b, mx = u3[("a", k)], u3[("b", k)], u3[("max", k)]
chk("U3 control (a): 20 cached, 81920", a["numBlocksCached"] == "20" and a["cacheUsed"] == "81920" and a["diskBytes"] == "81920"
    and a["f2FilesOnDisk"] == "4", "")
chk("U3 control (b): 0 refusals, Δ=4 duplicates", b["couldNotReserveNew"] == "0" and b["failedDelta"] == "4"
    and b["cacheUsed"] == "81920", "")
chk("U3 control max <= 81920", int(mx["maxCacheUsed"]) == 81920 and int(mx["maxDiskBytes"]) == 81920, "")

# ---------------- cluster
log = open(os.path.join(R, "cluster", "cluster-run.log")).read()
X = {}
for run, size in (("A0", 134217728), ("A", 268435456), ("B", 536870912)):
    sec = log.split("--- run %s:" % run)[1].split("--- run ")[0]
    xs = [int(v) for v in re.findall(r"Added persistent memory - \S+ with size=(\d+)", sec)]
    X[run] = xs[0]
    N = xs[0] // B
    s = list(csv.DictReader(open(os.path.join(R, "cluster", "samples-%s.csv" % run))))
    last = s[-1]
    mxb = max(int(r["cacheFileBytes"]) for r in s)
    mxu = max(int(r["CacheUsed"]) for r in s)
    mxdf = max(int(r["dfUsed"]) for r in s)
    chk("%s: one volume X=%d (S=%d), N=floor(X/B)=%d" % (run, xs[0], size, N), len(xs) == 1 and xs[0] <= size, "")
    chk("%s: final cached=N, CacheUsed=N*B, files=N*B" % run, int(last["NumBlocksCached"]) == N and int(last["CacheUsed"]) == N * B
        and int(last["cacheFileBytes"]) == N * B and int(last["cacheFiles"]) == N, str({x: last[x] for x in ("NumBlocksCached", "CacheUsed", "cacheFileBytes")}))
    chk("%s: max over %d samples <= X" % (run, len(s)), mxb <= xs[0] and mxu <= xs[0] and mxdf <= size,
        "maxFileBytes=%d maxCacheUsed=%d maxDfUsed=%d" % (mxb, mxu, mxdf))
    m = re.search(r"/f\s+(\d+)\s+(\d+)\s+1\s+0", sec)
    chk("%s: BYTES_CACHED=N*B of NEEDED" % run, m and int(m.group(2)) == N * B, m.group(0) if m else "none")
    cnt = dict(re.findall(r'dn "([^"]+)": (\d+)', sec))
    nnc = dict(re.findall(r'nn "([^"]+)": (\d+)', sec))
    chk("%s: no ENOSPC form, no refusal; NN rejects > 0" % run, all(cnt[p] == "0" for p in (
        "could not reserve more bytes", "Failed to cache the block", "No space left on device", "premature EOF",
        "checksum verification failed")) and int(nnc["is not a valid possibility because the block has size"]) > 0,
        "cached=%s rejects=%s" % (cnt["Successfully cached one replica"], nnc["is not a valid possibility because the block has size"]))
chk("dose: N rises with S (A0<A<B)", X["A0"] // B < X["A"] // B < X["B"] // B, "%d/%d/%d" % (X["A0"] // B, X["A"] // B, X["B"] // B))
sec = log.split("--- run C:")[1].split("--- run ")[0]
xs = [int(v) for v in re.findall(r"Added persistent memory - \S+ with size=(\d+)", sec)]
s = list(csv.DictReader(open(os.path.join(R, "cluster", "samples-C.csv"))))
cnt = dict(re.findall(r'dn "([^"]+)": (\d+)', sec))
dfsize = int(s[-1]["dfSize"])
chk("C: two volumes, capacity = 2X > df size", len(xs) == 2 and int(s[-1]["CacheCapacity"]) == sum(xs) and sum(xs) > dfsize,
    "X=%s cap=%s df=%d" % (xs, s[-1]["CacheCapacity"], dfsize))
chk("C: ENOSPC failures > 0", int(cnt["No space left on device"]) > 0 and int(cnt["Failed to cache the block"]) > 0,
    "noSpace=%s failed=%s" % (cnt["No space left on device"], cnt["Failed to cache the block"]))
chk("C: physical bound: <= floor(df/B) files, bytes <= df", max(int(r["cacheFiles"]) for r in s) <= dfsize // B
    and max(int(r["cacheFileBytes"]) for r in s) <= dfsize, "max files=%d" % max(int(r["cacheFiles"]) for r in s))
s = list(csv.DictReader(open(os.path.join(R, "cluster", "samples-D.csv"))))
chk("D: capacity 0, CacheUsed 0, nothing cached on the DN", all(r["CacheCapacity"] == "0" and r["CacheUsed"] == "0"
    and r["NumBlocksCached"] == "0" for r in s), "")
print("ALL OK" if ok_all else "SOME CHECK FAILED")
