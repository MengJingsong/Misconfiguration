#!/usr/bin/env python3
# Summarise cluster-tier arms (B3d observables) from the copied run folder.
# Usage: python3 -I analyze.py <cluster-out-dir>   (contains arm-<name>/)
import os, re, sys

UPD = re.compile(r"Update nonSequentialWriteInMemory by (-?\d+) new value: (\d+)")

def read(p):
    try:
        with open(p, errors="replace") as f:
            return f.read()
    except OSError:
        return ""

def num(pat, text):
    m = re.search(pat, text)
    return m.group(1) if m else "-"

base = sys.argv[1]
for arm in ["A", "B", "Aprime", "C", "D"]:
    d = os.path.join(base, "arm-" + arm)
    if not os.path.isdir(d):
        continue
    log = read(os.path.join(d, "nfs3.log"))
    hold = read(os.path.join(d, "nfs3-at-hold.log"))
    ups = [(int(a), int(b)) for a, b in UPD.findall(log)]
    pos = [v for by, v in ups if by > 0]
    neg = [by for by, v in ups if by < 0]
    hv = [int(b) for a, b in UPD.findall(hold)]
    jst = read(os.path.join(d, "jstat.txt")).splitlines()
    ou = []
    if jst:
        hdr = jst[0].split()
        if "OU" in hdr:
            i = hdr.index("OU")
            for line in jst[1:]:
                f = line.split()
                if len(f) == len(hdr) and f[0] != "S0C":
                    try:
                        ou.append(float(f[i]))
                    except ValueError:
                        pass
    client = read(os.path.join(d, "client.txt"))
    print("ARM", arm)
    print("  jar constant      :", read(os.path.join(d, "jar-const.txt")).strip())
    print("  updates +/-       :", len(pos), "/", len(neg))
    print("  log peak          :", max(pos) if pos else "-")
    print("  counter at hold   :", hv[-1] if hv else "-")
    print("  dump decr total   :", -sum(neg))
    print("  'Create dump file':", log.count("Create dump file"))
    print("  'Start dump' lines:", log.count("Start dump"))
    print("  dump create fail  :", log.count("Got failure when creating dump stream"))
    print("  stable->unstable  :", log.count("Have to change stable write to unstable write"))
    print("  OOM in log        :", log.count("OutOfMemoryError"))
    print("  H0 / H1           :", read(os.path.join(d, "H0.txt")).strip(), "|",
          read(os.path.join(d, "H1.txt")).strip() or read(os.path.join(d, "H1-end.txt")).strip())
    for f in ["dump-start.txt", "dump-hold.txt", "dump-after.txt", "dump-after-timeout.txt"]:
        t = read(os.path.join(d, f)).splitlines()
        if t:
            print("  %-18s: %s" % (f[:-4], t[0]))
    print("  hdfs stat         :", " ; ".join(read(os.path.join(d, "hdfs-stat.txt")).split("\n")).strip())
    print("  jstat OU KB min/max/last:", (min(ou), max(ou), ou[-1]) if ou else "-", "samples", len(ou))
    print("  client            :", " | ".join(l for l in client.splitlines()
                                           if not l.startswith("PROGRESS"))[:600])
    print("  last PROGRESS     :", ([l for l in client.splitlines() if l.startswith("PROGRESS")] or ["-"])[-1])
