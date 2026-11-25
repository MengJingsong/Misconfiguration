#!/usr/bin/env python3
"""Readings for o115 from the run logs. usage: analyze.py <outdir with *.log>"""
import re, sys, os, glob

D = sys.argv[1]
MiB = 1024 * 1024


def parse(path):
    r = {"resets": [], "live": [], "sizes": [], "exit": None, "warn": False}
    for line in open(path, errors="replace"):
        m = re.match(r"WRITER (\S+) LIMIT_BYTES (-?\d+)", line)
        if m: r["writer"], r["limit"] = m.group(1), int(m.group(2))
        m = re.match(r"H0_BYTES (\d+)", line)
        if m: r["h0"] = int(m.group(1))
        m = re.match(r"RESET (\d+) row (\d+) lastObserved (\d+)", line)
        if m: r["resets"].append((int(m.group(2)), int(m.group(3))))
        m = re.match(r"LIVE row (\d+) bytes (\d+)", line)
        if m: r["live"].append((int(m.group(1)), int(m.group(2))))
        m = re.match(r"SUMMARY limit=(-?\d+) resets=(\d+) maxObservedCurrentSize=(\d+) peakLive=(\d+) h0=(\d+)", line)
        if m: r["summary"] = tuple(int(x) for x in m.groups())
        m = re.match(r"^(\d+) (\S+-Data\.db)$", line.strip())
        if m: r["sizes"].append(int(m.group(1)))
        m = re.match(r"EXIT (\d+)", line)
        if m: r["exit"] = int(m.group(1))
        m = re.match(r"^(\d+)\s+(/\S+/probe/t)$", line.strip())
        if m: r["du"] = int(m.group(1))
        m = re.match(r"OOM_LINES (\d+)", line)
        if m: r["oom_lines"] = int(m.group(1))
        m = re.match(r"DATA_DB_COUNT (\d+)", line)
        if m: r["count"] = int(m.group(1))
        if "A non-positive value for maximum SSTable size is specified" in line: r["warn"] = True
    return r


print("## Unit tier")
for R in ["U1", "U2", "U3", "U4", "U5"]:
    p = os.path.join(D, f"unit-{R}.log")
    if not os.path.exists(p): print(R, "missing"); continue
    r = parse(p)
    s = r.get("summary")
    sz = sorted(r["sizes"], reverse=True)
    lo = [x[1] for x in r["resets"]]
    print(f"{R}: exit={r['exit']} writer={r.get('writer')} LIMIT_BYTES={r.get('limit')} resets={len(r['resets'])}"
          f" maxObserved={s[2] if s else None} lastObserved[min,max]={[min(lo), max(lo)] if lo else '-'}"
          f" reset_rows={[x[0] for x in r['resets']][:3]}... DataDb={r.get('count')} warn={r['warn']}")
    if sz:
        big = [x for x in sz if x > 20e6] if R != "U4" else sz
        print(f"    sizes: n={len(sz)} largest={sz[0]} smallest={sz[-1]} big[min,max]={[min(big), max(big)] if big else '-'} du={r.get('du')}")

print("\n## Cluster tier: live-heap runs")
peaks = {}
for R, B in [("C16", 16), ("C32", 32), ("C64", 64), ("C128", 128), ("CX", 2047)]:
    p = os.path.join(D, f"{R}.log")
    if not os.path.exists(p): print(R, "missing"); continue
    r = parse(p)
    h0 = r["h0"]
    lv = [(row, (b - h0) / MiB) for row, b in r["live"]]
    n = len(lv); t = n // 3
    first = sum(x[1] for x in lv[:t]) / t
    last = sum(x[1] for x in lv[-t:]) / t
    s = r["summary"]
    pk = (s[3] - h0) / MiB
    peaks[R] = pk
    sz = sorted(r["sizes"], reverse=True)
    print(f"{R}: exit={r['exit']} H0={h0/MiB:.1f}MiB samples={n} peakLive-H0={pk:.1f}MiB"
          f" mean(last third)-mean(first third)={last-first:.1f}MiB (flat bound {max(0.5*B,16):.0f})"
          f" min/max(LIVE-H0)={min(x[1] for x in lv):.1f}/{max(x[1] for x in lv):.1f}"
          f" DataDb={r.get('count')} du={r.get('du')}")
    if sz:
        print(f"    sizes: largest={sz[0]} 2nd-smallest={sz[-2] if len(sz)>1 else '-'} smallest={sz[-1]}"
              f" big[min,max]={[min(sz[:-1]), max(sz[:-1])] if len(sz)>1 else '-'}")
    print("    LIVE-H0 MiB series:", " ".join(f"{x[1]:.0f}" for x in lv))
if "C128" in peaks and "C16" in peaks:
    print(f"peak(C128)-peak(C16) = {peaks['C128']-peaks['C16']:.1f} MiB (band 100-260)")
cs = [peaks[k] for k in ("C16", "C32", "C64", "C128") if k in peaks]
if cs: print(f"max-min peak over C16..C128 = {max(cs)-min(cs):.1f} MiB (row 3 if <= 30)")

print("\n## Cluster tier: OOM sweep")
for p in sorted(glob.glob(os.path.join(D, "oom-*.log"))):
    r = parse(p)
    print(f"{os.path.basename(p)}: exit={r['exit']} OOM_LINES={r.get('oom_lines')} DataDb={r.get('count')}")
