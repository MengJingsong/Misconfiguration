#!/usr/bin/env python3
"""Self-check for dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous (stage 4, run 1).

usage: selfcheck.py <unit ifchk.csv> <ablate ifchk.csv> <cluster-run.log>
Re-parses the raw IFCHK lines (surefire output) and CLCHK lines (cluster log) and compares each value with the frozen
predictions B2f/B3f + A3/A7 of the amended case file. Prints PASS/FAIL per check and totals.
"""
import re, sys

res = []


def chk(name, ok, got):
    res.append(ok)
    print(("PASS" if ok else "FAIL"), name, "->", got)


def kv(line):
    d = {}
    for part in line.strip().split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            d[k] = v
    return d


unit = [l for l in open(sys.argv[1]) if l.startswith("IFCHK,")]
abl = [l for l in open(sys.argv[2]) if l.startswith("IFCHK,")]
clus = [l[l.index("CLCHK,"):] for l in open(sys.argv[3]) if "CLCHK," in l and not l.startswith("+")]

# ---------------- unit, Test A
A = [kv(l) for l in unit if l.startswith("IFCHK,A,")]
chk("unit A: 3 rows", len(A) == 3, len(A))
for d in A:
    c = int(d["C"])
    p = f"unit A C={c}:"
    chk(p + " settled", d["settled"] == "true", d["settled"])
    chk(p + " dnCacheUsed = C", int(d["dnCacheUsed"]) == c, d["dnCacheUsed"])
    chk(p + " dnBlocks = C/4096", int(d["dnBlocks"]) == c // 4096, d["dnBlocks"])
    chk(p + " bytesCached = C", int(d["bytesCached"]) == c, d["bytesCached"])
    chk(p + " nnPendingBytes = 0", int(d["nnPendingBytes"]) == 0, d["nnPendingBytes"])
    chk(p + " maxDnCacheUsed <= C", int(d["maxDnCacheUsed"]) <= c, d["maxDnCacheUsed"])
    print("INFO", p, "dnFailed =", d["dnFailed"], "dropLines =", d["dropLines"], "dropIds =", d["dropIds"])

# ---------------- unit, Test B
B = [kv(l) for l in unit if l.startswith("IFCHK,B,")]
chk("unit B: 9 rows", len(B) == 9, len(B))
for d in B:
    v = int(d["v"])
    head = 65536 - v if d["mode"] == "U" else v
    p1 = 4096 * max(0, head // 4096)
    nd = 16 - p1 // 4096
    p = f"unit B {d['mode']}={v}:"
    chk(p + " P0 = 65536 (16)", int(d["P0"]) == 65536 and int(d["P0n"]) == 16, (d["P0"], d["P0n"]))
    chk(p + " pre lines = 0", int(d["pre_dropLines"]) == 0, d["pre_dropLines"])
    chk(p + f" remaining = {head}", int(d["remaining"]) == head, d["remaining"])
    chk(p + f" P1 = {p1}", int(d["P1"]) == p1 and int(d["P1n"]) == p1 // 4096, (d["P1"], d["P1n"]))
    chk(p + " P2 = P1", d["P2"] == d["P1"] and d["P2n"] == d["P1n"], (d["P2"], d["P2n"]))
    chk(p + f" w1 ids = {nd}, lines = ids", int(d["w1_dropIds"]) == nd and int(d["w1_dropLines"]) == nd,
        (d["w1_dropLines"], d["w1_dropIds"]))
    chk(p + " w2 lines = 0", int(d["w2_dropLines"]) == 0, d["w2_dropLines"])
    chk(p + " DN cached nothing (heartbeats off)", int(d["dnCacheUsed"]) == 0, d["dnCacheUsed"])

C = [kv(l) for l in unit if l.startswith("IFCHK,C,")]
chk("unit C: 1 row", len(C) == 1, len(C))
for d in C:
    chk("unit C: settled", d["settled"] == "true", d["settled"])
    chk("unit C: dnCacheUsed = 65536", int(d["dnCacheUsed"]) == 65536, d["dnCacheUsed"])
    print("INFO unit C: dnFailed =", d["dnFailed"], "maxDnCacheUsed =", d["maxDnCacheUsed"])

AB = [kv(l) for l in abl if l.startswith("IFCHK,B,")]
chk("ablation: 1 row", len(AB) == 1, len(AB))
for d in AB:
    chk("ablation U=49152: P0 = 65536", int(d["P0"]) == 65536, d["P0"])
    chk("ablation U=49152: P1 = 65536", int(d["P1"]) == 65536, d["P1"])
    chk("ablation U=49152: P2 = 65536", int(d["P2"]) == 65536, d["P2"])
    chk("ablation U=49152: w1 lines = 0", int(d["w1_dropLines"]) == 0, d["w1_dropLines"])

# ---------------- cluster, phase 1
MiB = 1048576
want = {"M0": (0, 0), "M64m": (64 * MiB, 64 * MiB), "M128m": (128 * MiB, 128 * MiB),
        "M256m": (256 * MiB, 256 * MiB), "M1g": (1024 * MiB, 512 * MiB)}
P = {}
for l in clus:
    f = l.split(",")
    P[f[1]] = kv(l)
for ph, (m, used) in want.items():
    d = P.get(ph)
    chk(f"cluster {ph}: present", d is not None, ph)
    if not d:
        continue
    p = f"cluster {ph} (M={m}):"
    chk(p + " settled", d["settled"] == "True", d["settled"])
    chk(p + f" CacheUsed = {used}", int(d["CacheUsed"]) == used, d["CacheUsed"])
    chk(p + f" NumBlocksCached = {used // (16 * MiB)}", int(d["NumBlocksCached"]) == used // (16 * MiB), d["NumBlocksCached"])
    chk(p + f" BYTES_CACHED = {used}", int(d["BYTES_CACHED"] or -1) == used, d["BYTES_CACHED"])
    chk(p + f" VmLck delta = {used // 1024} kB +- 1024", abs(int(d["VmLckDelta_kB"]) - used // 1024) <= 1024, d["VmLckDelta_kB"])
    if m < 512 * MiB:
        chk(p + " max CacheUsed <= M", int(d["maxCacheUsed"]) <= m, d["maxCacheUsed"])
        chk(p + " max VmLck delta <= M + 1 MiB", int(d["maxVmLckDelta_kB"]) <= m // 1024 + 1024, d["maxVmLckDelta_kB"])
    print("INFO", p, "CacheCapacity", d["CacheCapacity"], "failed", d["NumBlocksFailedToCache"],
          "dropLines", d["dropLines"], "dropIds", d["dropIds"], "dnaCacheLines", d["dnaCacheLines"], "t", d["t"])

# ---------------- cluster, phase 2
d = P.get("P2-M128m")
chk("cluster P2: present", d is not None, "P2-M128m")
if d:
    m = 128 * MiB
    crt = d["firstCacheReport_t"]
    chk("cluster P2: window to next cache report >= 20 s", crt not in ("None",) and float(crt) >= 20, crt)
    chk("cluster P2: 'cannot fit' distinct ids in 1..8", 1 <= int(d["dropIds"]) <= 8, (d["dropLines"], d["dropIds"]))
    chk("cluster P2: first 'cannot fit' within ~3 s (<= 5 s)", d["dropFirst_t"] != "-" and float(d["dropFirst_t"]) <= 5,
        d["dropFirst_t"])
    chk("cluster P2: DNA_CACHE lines before the cache report in 1..3", 1 <= int(d["dnaCacheLinesBeforeCR"]) <= 3,
        (d["dnaCacheLinesBeforeCR"], d["dnaCache_t"]))
    chk("cluster P2: DNA_CACHE distinct ids <= 8", int(d["dnaCacheIds"]) <= 8, d["dnaCacheIds"])
    chk("cluster P2: final CacheUsed = 134217728", int(d["CacheUsed"]) == m, d["CacheUsed"])
    chk("cluster P2: VmLck delta = 131072 kB +- 1024", abs(int(d["VmLckDelta_kB"]) - 131072) <= 1024, d["VmLckDelta_kB"])
    chk("cluster P2: max CacheUsed <= M", int(d["maxCacheUsed"]) <= m, d["maxCacheUsed"])

print(f"TOTAL: {sum(res)} PASS, {len(res) - sum(res)} FAIL")
