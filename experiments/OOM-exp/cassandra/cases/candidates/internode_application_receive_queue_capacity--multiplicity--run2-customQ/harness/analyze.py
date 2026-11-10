#!/usr/bin/env python3
# Analyze an arm's queue.log timeseries (internode_inbound snapshots) + mem.csv.
# Usage: analyze.py <arm_dir>
import sys, os
d = sys.argv[1]
ql = os.path.join(d, "queue.log")
blocks = []
cur = None
for line in open(ql):
    line = line.strip()
    if line.startswith("@"):
        if cur is not None:
            blocks.append(cur)
        cur = {"t": line.split()[1], "ub": 0, "rb": 0, "nz": 0, "rcv": {}, "thr": 0}
    elif line.startswith("10.10.1.") and cur is not None:
        f = [x.strip() for x in line.split("|")]
        # address|using_bytes|using_reserve_bytes|throttled_count|received_count|processed_count
        if len(f) >= 6 and f[1].isdigit():
            ub = int(f[1]); rb = int(f[2]); thr = int(f[3]); rc = int(f[4])
            cur["ub"] += ub; cur["rb"] += rb; cur["thr"] += thr
            cur["rcv"][f[0]] = rc
            if ub > 0:
                cur["nz"] += 1
if cur:
    blocks.append(cur)

MiB = 1048576.0
print("queue samples:", len(blocks))
peak = max(blocks, key=lambda b: b["ub"]) if blocks else None
peakr = max(blocks, key=lambda b: b["rb"]) if blocks else None
for b in blocks:
    if b["ub"] > 0 or b["rb"] > 0:
        print("  t=%s sum_using=%.1fMiB sum_reserve=%.1fMiB nonzero_peers=%d throttled=%d" % (
            b["t"], b["ub"]/MiB, b["rb"]/MiB, b["nz"], b["thr"]))
if peak:
    print("PEAK sum_using=%.1fMiB (reserve at that sample=%.1fMiB, nonzero_peers=%d)" % (
        peak["ub"]/MiB, peak["rb"]/MiB, peak["nz"]))
if peakr:
    print("PEAK sum_reserve=%.1fMiB (using at that sample=%.1fMiB)" % (peakr["rb"]/MiB, peakr["ub"]/MiB))
# coordinators that received traffic (last sample received_count)
if blocks:
    last = blocks[-1]["rcv"]
    nz = sorted((k, v) for k, v in last.items() if v > 0)
    print("peers with received_count>0 (final): %d ->" % len(nz), [k for k, _ in nz])

# mem.csv peaks
mc = os.path.join(d, "mem.csv")
if os.path.exists(mc):
    mra = mmc = 0; oom = ok = 0
    for i, line in enumerate(open(mc)):
        if i == 0:
            continue
        p = line.strip().split(",")
        if len(p) < 5:
            continue
        if p[1] != "NA":
            mra = max(mra, int(p[1]))
        if p[2] != "NA":
            mmc = max(mmc, int(p[2]))
        if p[3] not in ("NA", ""):
            oom = p[3]
        if p[4] not in ("NA", ""):
            ok = p[4]
    print("mem: peak_rssAnon=%.0fMiB peak_mem_current=%.0fMiB oom=%s oom_kill=%s" % (
        mra/1024.0, mmc/MiB, oom, ok))
