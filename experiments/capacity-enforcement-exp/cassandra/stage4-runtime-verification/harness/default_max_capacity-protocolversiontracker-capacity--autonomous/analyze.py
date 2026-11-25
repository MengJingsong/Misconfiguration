#!/usr/bin/env python3
"""o134 analysis. Usage: analyze.py <run-dir>   (run-dir holds unit/ and cluster/{stock,uncapped}/)
Unit: medians over the 3 reps per (cap, N). Cluster: histogram deltas vs h-0 for the B3d classes and the
Caffeine class whose count rises by ~N in the uncapped control."""
import re, sys, os, statistics as st
R = sys.argv[1]

def unit():
    rows = {}
    for f in sorted(os.listdir(f"{R}/unit")):
        m = re.match(r"c(\d+)-n(\d+)-r(\d)\.out$", f)
        if not m: continue
        t = open(f"{R}/unit/{f}").read()
        a = dict(re.findall(r"(\w[\w.]*)=(-?\d+)", t.splitlines()[0]))
        b = dict(re.findall(r"(\d/v[\w-]+)=(\d+)", t.splitlines()[1]))
        tot = re.search(r"total=(\d+)", t.splitlines()[1]).group(1)
        rows.setdefault((int(m[1]), int(m[2])), []).append((a, b, int(tot)))
    print("UNIT cap N | V4.size(getAll) per rep | maxRaw per rep | heapDelta median (B) | after pass2 V3/V5/V6/total")
    for (cap, n), L in sorted(rows.items()):
        sz = [f"{x[0]['V4.estimatedSize']}({x[0]['V4.getAll']})" for x in L]
        print(f"{cap} {n} | {' '.join(sz)} | {' '.join(x[0]['maxRawBeforeCleanup'] for x in L)} | "
              f"{int(st.median(int(x[0]['heapDeltaBytes']) for x in L))} | "
              f"{L[0][1]['3/v3']}/{L[0][1]['5/v5']}/{L[0][1]['6/v6-beta']}/{L[0][2]} (reps agree: {len({(tuple(x[1].items()), x[2]) for x in L}) == 1})")

def hist(p):
    d = {}
    for line in open(p):
        m = re.match(r"\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)", line)
        if m: d[m[3]] = (int(m[1]), int(m[2]))
    return d

def cluster():
    steps = ["0", "v4-50", "v4-100", "v4-150", "v4-1000", "v4-20000", "all", "repeat", "clear"]
    hs = {b: {s: hist(f"{R}/cluster/{b}/h-{s}.txt") for s in steps if os.path.exists(f"{R}/cluster/{b}/h-{s}.txt")}
          for b in ("stock", "uncapped") if os.path.isdir(f"{R}/cluster/{b}")}
    node = None
    if "uncapped" in hs and "v4-20000" in hs["uncapped"]:
        h0, h1 = hs["uncapped"]["0"], hs["uncapped"]["v4-20000"]
        cands = sorted(((h1[c][0] - h0.get(c, (0, 0))[0], c) for c in h1 if c.startswith("com.github.benmanes.caffeine")), reverse=True)
        print("uncapped: caffeine classes by count rise 0 -> v4-20000:", cands[:4]); node = cands[0][1]
    cls = ["java.net.Inet4Address", "java.net.InetAddress$InetAddressHolder", "java.lang.Long"] + ([node] if node else [])
    extra = ["java.util.concurrent.ConcurrentHashMap$Node"]
    for b, H in hs.items():
        print(f"\nCLUSTER {b}: count delta vs h-0 (bytes delta)   classes: {cls + extra}")
        for s in steps[1:]:
            if s not in H: continue
            ds = [(H[s].get(c, (0, 0))[0] - H["0"].get(c, (0, 0))[0], H[s].get(c, (0, 0))[1] - H["0"].get(c, (0, 0))[1]) for c in cls + extra]
            summ = sum(x[1] for x in ds[:len(cls)])
            print(f"  {s:9s} " + "  ".join(f"{x[0]:+d}({x[1]:+d})" for x in ds) + f"   SUM(B3d classes)={summ:+d} B")

if os.path.isdir(f"{R}/unit"): unit()
if os.path.isdir(f"{R}/cluster"): cluster()
