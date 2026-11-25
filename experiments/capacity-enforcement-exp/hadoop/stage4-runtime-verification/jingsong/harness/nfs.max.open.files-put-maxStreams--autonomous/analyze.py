#!/usr/bin/env python3
"""Tabulate the cluster-tier samples for nfs.max.open.files-put-maxStreams--autonomous.
Usage: python3 -I analyze.py <cluster-dir>   (the run's logs/cluster folder)"""
import os, re, sys
d = sys.argv[1]
arms = ["K8", "K32", "K128", "Kdefault", "K8null"]
kv = lambda line: dict(re.findall(r'(\w+)=(\S+)', line))
print("| arm | client SUMMARY | log counts (max-streams line / Can't add new / Can't add more / evict) |")
print("|---|---|---|")
rows = []
for a in arms:
    A = os.path.join(d, "arm-" + a)
    if not os.path.isdir(A):
        continue
    cl = open(os.path.join(A, "client.txt")).read()
    summ = re.search(r'^SUMMARY (.*)$', cl, re.M)
    lc = {}
    for line in open(os.path.join(A, "logcounts.txt")):
        m = re.match(r"LOGCOUNT (.*): (\d+)", line.strip())
        if m:
            lc[m.group(1)] = int(m.group(2))
    g = open(os.path.join(A, "gateway.log")).read()
    ms = re.findall(r'Maximum open streams is (\d+)', g)
    print(f"| {a} | {summ.group(1) if summ else 'none'} | {ms[:1]} / {lc.get(chr(67)+'an'+chr(39)+'t add new stream')} / "
          f"{lc.get(chr(67)+'an'+chr(39)+'t add more stream')} / {lc.get('Evict stream ctx')} |")
    S = {}
    for line in open(os.path.join(A, "samples.txt")):
        s = kv(line)
        S[s["tag"]] = s
    rows.append((a, S))
print()
print("| arm | sample | OpenFileCtx | WriteCtx | DFSOutputStream | DataStreamer threads | listOpenFiles | heap used after GC (MiB) | delta vs base (MiB) | [B delta (MiB) | dump files | RSS (MiB) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for a, S in rows:
    b = S.get("base")
    for tag in ["base", "s15", "s45", "s90"]:
        s = S.get(tag)
        if not s:
            continue
        hu = int(s["heapUsedK"]) / 1024
        dh = (int(s["heapUsedK"]) - int(b["heapUsedK"])) / 1024
        db = (int(s["B_bytes"]) - int(b["B_bytes"])) / 1048576
        print(f"| {a} | {tag} | {s['OpenFileCtx']} | {s['WriteCtx']} | {s['DFSOutputStream']} | {s['streamers']} | "
              f"{s['openFiles']} | {hu:.2f} | {dh:+.2f} | {db:+.2f} | {s['dumpFiles']} | {int(s['rssK'])/1024:.0f} |")
