#!/usr/bin/env python3
"""Self-check: re-derives the cited numbers from the raw files with its own parsing (not the analyzers' code).
usage: selfcheck.py <run-dir>     (<run-dir>/unit/TEST-*.log, <run-dir>/<cfg>/{events.txt,samples.csv,jstack/,logs/system.log})"""
import csv
import glob
import os
import re
import sys

R = sys.argv[1]
MIB = 1 << 20
print("== unit: raw CAP lines (bytes) ==")
for f in sorted(glob.glob(f"{R}/unit/TEST-*CommitLogBufferCap*.log")):
    pre = None
    for ln in open(f, errors="replace"):
        m = re.search(r"CAP (\S+) (\S+) N=(\d+) active=(\d+) pool=\[(.*?)\] directUsed=(\d+)", ln)
        if not m:
            continue
        cls, lab, n, act, pool, du = m.groups()
        du = int(du)
        if lab == "pre-writer":
            pre = du
        ub = re.search(r"usedBuffers:(\d+)", pool)
        print(f"{cls:28s} {lab:18s} N={n} active={act:>2s} used={ub.group(1) if ub else '-':>2s} "
              f"direct-pre={du - pre} B = {(du - pre) / MIB:.4f} MiB; minus (N-2) MiB = {du - pre - (int(n) - 2) * MIB if 'Ctl' not in cls else '-'} B")
    junit = f.replace(".log", ".xml")
    if os.path.exists(junit):
        x = open(junit).read()
        print("   junit:", re.search(r'tests="\d+"[^>]*', x).group(0)[:120] if re.search(r'tests="\d+"[^>]*', x) else "?")
for f in sorted(glob.glob(f"{R}/unit/TEST-*SimpleCachedBufferPoolCapTest.log")):
    for ln in open(f, errors="replace"):
        if "step=construct exception" in ln or "step=released2N" in ln or "step=retakeN" in ln:
            print("  ", ln[ln.find("POOL"):].strip()[:200])

print("== cluster ==")
for cfg in ("N3", "N6", "N12", "C1", "C2", "N1"):
    d = f"{R}/{cfg}"
    if not os.path.isdir(d):
        continue
    ev = {}
    for ln in open(f"{d}/events.txt"):
        k, v = ln.split()
        ev.setdefault(k, int(v))
    sl = f"{d}/logs/system.log"
    errs = sum(1 for ln in open(sl, errors="replace") if ln.startswith("ERROR")) if os.path.exists(sl) else -1
    oom = sum(1 for ln in open(sl, errors="replace") if "OutOfMemoryError" in ln) if os.path.exists(sl) else -1
    pool_line = ""
    if os.path.exists(sl):
        for ln in open(sl, errors="replace"):
            if "commitlog_max_compression_buffers_in_pool=" in ln:
                pool_line = re.search(r"commitlog_max_compression_buffers_in_pool=\d+", ln).group(0)
                cl = re.search(r"commitlog_compression=[^;]*?(?=; )", ln)
                pool_line += " " + (cl.group(0)[:120] if cl else "")
                break
    print(f"-- {cfg}: config echo: {pool_line}; ERROR lines {errs}; OutOfMemoryError lines {oom}")
    if cfg == "N1" or not os.path.exists(f"{d}/samples.csv"):
        if os.path.exists(f"{d}/n1-excerpt.txt"):
            print("   ", open(f"{d}/n1-excerpt.txt").read()[:600].replace("\n", "\n    "))
        continue
    s0, s1 = ev["stress_start"], ev["stress_end"]
    rows = [r for r in csv.DictReader(l for l in open(f"{d}/samples.csv") if not l.startswith("#"))]
    idle = sorted(int(r["direct_used"]) for r in rows if s0 - 30000 <= int(r["epoch_ms"]) <= s0)
    win = [(int(r["epoch_ms"]), int(r["direct_used"]), int(r["wosa_count"])) for r in rows if s0 <= int(r["epoch_ms"]) <= s1]
    med = idle[len(idle) // 2] if len(idle) % 2 else (idle[len(idle) // 2 - 1] + idle[len(idle) // 2]) / 2
    pk = max(win, key=lambda x: x[1])
    print(f"   idle n={len(idle)} median={med / MIB:.2f} MiB; window n={len(win)} max={pk[1] / MIB:.2f} MiB at +{(pk[0] - s0) / 1000:.0f}s; "
          f"P-B0={(pk[1] - med) / MIB:.2f} MiB; WOSA {win[0][2]}->{win[-1][2]}")
    nb = 0
    for f in sorted(glob.glob(f"{d}/jstack/*.txt")):
        t = int(os.path.basename(f)[:-4])
        if not s0 <= t <= s1:
            continue
        txt = open(f, errors="replace").read()
        a = re.search(r'^"COMMIT-LOG-ALLOCATOR.*?(?=\n\n)', txt, re.S | re.M)
        w = txt.count("awaitAvailableSegment")
        if a and "waitOnCondition" in a.group(0) and w:
            nb += 1
    print(f"   jstack dumps in window with allocator waiting + writer in awaitAvailableSegment: {nb}")
