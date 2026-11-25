#!/usr/bin/env python3
"""Readings and A3/A4 (unit) and A6/A7 (cluster) checks for
dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.

Usage: python3 -I analyze.py <logs dir copied from the node>   (contains unit/ and cluster/ and cluster-run.log)
Prints a readings table and a PASS/FAIL line per frozen condition. Does not decide the verdict.
"""
import glob
import os
import re
import statistics
import sys

D = sys.argv[1]
MiB = 1048576
ok_all = {"unit": [], "cluster": []}


def check(tier, name, cond, detail):
    ok_all[tier].append(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}: {detail}")


# ---------------------------------------------------------------- unit
def rows(mode):
    p = os.path.join(D, "unit", f"readings-{mode}.csv")
    return [l.strip().split(",") for l in open(p) if not l.startswith("+")]


print("== UNIT (A3/A4)")
for mode in ("managed", "disabled", "mutation"):
    R = rows(mode)
    env = [r for r in R if r[0] == "ENV"]
    for e in env:
        check("unit", f"{mode} {e[1]} argLine", e[4] == "1037959168" and "MarkSweepCompact" in e[5] and "-Xmx1g" in e[6],
              f"maxHeap={e[4]} gc={e[5]}")
    k = [r for r in R if r[0] == "KNOWN"][0]
    check("unit", f"{mode} known answer", 0 <= int(k[4]) <= 131072, f"delta={k[4]}")
    exits = [r for r in R if r[0] == "CHILD-EXIT"]
    check("unit", f"{mode} children exit 0", len(exits) == 16 and all(r[5] == "0" for r in exits), f"n={len(exits)}")
    c1 = [r for r in R if r[0] == "CASE1"]
    for r in c1:
        L, rep, pAfter, pMax, pFinal, delta = int(r[2]), int(r[3]), int(r[4]), int(r[5]), int(r[6]), int(r[9])
        print(f"    CASE1 {mode} L={L:5d} rep={rep} poolAfterManaged={pAfter} maxExtra={pMax} final={pFinal} delta={delta}")
        if mode == "managed":
            check("unit", f"managed L={L} rep={rep} pool", pAfter == L and pMax == L and pFinal == L, f"{pAfter}/{pMax}/{pFinal}")
            if L == 64:
                check("unit", f"managed L=64 rep={rep} delta", 3145728 <= delta <= 6292480, str(delta))
            if L == 1024:
                check("unit", f"managed L=1024 rep={rep} delta", 66060288 <= delta <= 69222400, str(delta))
        elif mode == "disabled":
            check("unit", f"disabled L={L} rep={rep}", pAfter == 0 and pMax == 0 and pFinal == 0 and abs(delta) <= MiB,
                  f"{pAfter}/{pMax}/{pFinal} delta={delta}")
        else:
            check("unit", f"mutation L={L} rep={rep} pool", pAfter == L and pFinal == 2 * L + 10, f"{pAfter}/{pFinal}")
            if L == 1024:
                check("unit", f"mutation L=1024 rep={rep} delta", delta >= 133824512, str(delta))
    if mode == "managed":
        for r in [r for r in R if r[0] == "CASE2"]:
            check("unit", f"case2 L={r[1]}", r[4] == "WAITING" and r[5] == "TERMINATED" and int(r[6]) <= 1000,
                  f"{r[4]}->{r[5]} in {r[6]} ms")
        c3 = [r for r in R if r[0] == "CASE3" and r[1] == "release"]
        check("unit", "case3 pool <= 4 after every release", all(int(r[4]) <= 4 for r in c3), " ".join(r[4] for r in c3))
        check("unit", "case3 final pool 4", c3[-1][4] == "4", c3[-1][5])
        check("unit", "case3 numAllocated 0 after 4th unmanaged release", c3[3][5].startswith("[65536: 0/4"), c3[3][5])
        w = {r[1]: r for r in R if r[0] == "WIRE"}
        check("unit", "wiring on", w["on"][2].endswith("$Impl") and w["on"][4] == "[65536: 1/16; free=0]", ",".join(w["on"][2:]))
        check("unit", "wiring off", w["off"][2].endswith("$NewByteArrayWithoutLimit"), w["off"][2])
print(f"UNIT: {sum(ok_all['unit'])}/{len(ok_all['unit'])} conditions pass")

# ---------------------------------------------------------------- cluster
print("\n== CLUSTER (A6/A7)")
log = open(os.path.join(D, "cluster-run.log")).read()
samples, post, rc, du = {}, {}, {}, {}
for m in re.finditer(r"^SAMPLE (\S+) s(\d) \d+\s+\d+:\s+\d+\s+(\d+)\s+\[B$", log, re.M):
    samples.setdefault(m.group(1), []).append(int(m.group(3)))
for m in re.finditer(r"POSTGC tag=(\S+) heapUsed=(\d+) manager1M=(.*?) manager64=(.*?) failures=(\d+) writeMs=(\d+)", log):
    post[m.group(1)] = m.groups()
for m in re.finditer(r"^PROBE-EXIT (\S+) rc=(\d+)", log, re.M):
    rc[m.group(1)] = int(m.group(2))
for m in re.finditer(r"^(\d+)\s+\d+\s+/bam/(\S+)$", log, re.M):
    du[m.group(2)] = int(m.group(1))
heap = {}
for p in glob.glob(os.path.join(D, "cluster", "probe-*.log")):
    t = os.path.basename(p)[6:-4]
    m = re.search(r"maxHeap=(\d+) gc=(\S+)", open(p).read())
    heap[t] = m.groups() if m else None

tags = ["disabled", "L8", "L16", "L32", "L4096", "L8t32"]
reading = {}
for t in tags:
    for rep in (1, 2, 3):
        i = f"{t}-r{rep}"
        if i in samples and len(samples[i]) == 3:
            reading[i] = statistics.median(samples[i])
dis = [reading[f"disabled-r{r}"] for r in (1, 2, 3) if f"disabled-r{r}" in reading]
B = statistics.median(dis) if len(dis) == 3 else None
print(f"B (median of disabled readings) = {B}  from {dis}")
band = {"L8": (6291584, 10485888), "L8t32": (6291584, 10485888), "L16": (14680320, 18874624), "L32": (31457792, 35652096)}
for t in tags:
    for rep in (1, 2, 3):
        i = f"{t}-r{rep}"
        if i not in post:
            check("cluster", f"{i} ran", False, "no POSTGC line")
            continue
        heapUsed, m1, m64, fails, ms = post[i][1], post[i][2], post[i][3], post[i][4], post[i][5]
        rd = reading.get(i)
        delta = rd - B if (rd is not None and B is not None) else None
        print(f"    {i:12s} samples={samples.get(i)} reading={rd} delta={delta} mgr1M={m1} mgr64={m64} heapUsed={heapUsed} writeMs={ms} rc={rc.get(i)} du={du.get(i)} maxHeap={heap.get(i)}")
        check("cluster", f"{i} workload", rc.get(i) == 0 and fails == "0" and du.get(i) == 4294967296, f"rc={rc.get(i)} du={du.get(i)}")
        check("cluster", f"{i} probe heap 1 GiB serial", heap.get(i) is not None and heap[i][0] == "1037959168" and "MarkSweepCompact" in heap[i][1], str(heap.get(i)))
        if t == "disabled":
            check("cluster", f"{i} no manager, within B±2MiB", m1.startswith("no manager") and abs(delta) <= 2 * MiB, f"{m1} delta={delta}")
        elif t == "L4096":
            k = int(re.search(r"free=(\d+)", m1).group(1)) if "free=" in m1 else -1
            check("cluster", f"{i} control free k in [64,384] and |delta-k*1048592|<=2MiB",
                  64 <= k <= 384 and abs(delta - k * 1048592) <= 2 * MiB, f"k={k} delta={delta} k*1048592={k*1048592}")
            check("cluster", f"{i} limit /4096", "/4096," in m1, m1)
        else:
            L = 8 if t.startswith("L8") else int(t[1:])
            check("cluster", f"{i} manager string", m1 == f"[1048576: 0/{L}, free={L}]", m1)
            lo, hi = band[t]
            check("cluster", f"{i} delta band", lo <= delta <= hi, f"{lo} <= {delta} <= {hi}")
print(f"CLUSTER: {sum(ok_all['cluster'])}/{len(ok_all['cluster'])} conditions pass")
