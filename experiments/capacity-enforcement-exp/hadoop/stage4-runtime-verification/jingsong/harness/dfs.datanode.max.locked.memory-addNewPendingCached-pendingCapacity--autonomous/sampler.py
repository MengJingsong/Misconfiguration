#!/usr/bin/env python3
"""Cluster-tier sampler (B3d + A5) for dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.

usage: sampler.py <phase> <C> <path> <t0_epoch> <nnlog> <nnlog_off> <dnlog> <dnlog_off> <dnpid> <vmlck_base_kB> <csv>
Every 5 s: DataNode VmLck (/proc/<pid>/status), DataNode JMX FSDatasetState (CacheCapacity, CacheUsed,
NumBlocksCached, NumBlocksFailedToCache), `hdfs cacheadmin -listDirectives -stats -path <path>`
(BYTES_NEEDED, BYTES_CACHED, FILES_CACHED) and `hdfs dfsadmin -report` (Cache Used, Cache Remaining).
Plateau (A5): at least 60 s after the directive and the last 4 samples equal on
(CacheUsed, NumBlocksCached, NumBlocksFailedToCache, VmLck, BYTES_CACHED); at most 120 s (settled=false).
Prints one CLCHK line with the final reading, maxima, and the log-line counts since the offsets.
"""
import csv, json, os, re, subprocess, sys, time, urllib.request

phase, C, path, t0, nnlog, nnoff, dnlog, dnoff, dnpid, base, out = sys.argv[1:12]
C = int(C); t0 = float(t0); nnoff = int(nnoff); dnoff = int(dnoff); base = int(base)
REJ = "is not a valid possibility because the block has size"
ADD = "added to PENDING_CACHED on DataNode"
INS = "have insufficient cache capacity"
NORES = "could not reserve more bytes"


def vmlck():
    with open(f"/proc/{dnpid}/status") as f:
        for line in f:
            if line.startswith("VmLck:"):
                return int(line.split()[1])
    return -1


def jmx():
    u = "http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*"
    b = json.load(urllib.request.urlopen(u, timeout=10))["beans"][0]
    return b["CacheCapacity"], b["CacheUsed"], b["NumBlocksCached"], b["NumBlocksFailedToCache"]


def dstats():
    r = subprocess.run(["hdfs", "cacheadmin", "-listDirectives", "-stats", "-path", path],
                       capture_output=True, text=True, timeout=60)
    hdr = None
    for l in r.stdout.splitlines():
        f = l.split()
        if f and f[0] == "ID":
            hdr = f
        elif hdr and f and f[0].isdigit():
            return dict(zip(hdr, f))
    return {}


def report():
    r = subprocess.run(["hdfs", "dfsadmin", "-report"], capture_output=True, text=True, timeout=60)
    d = {}
    for k in ("Configured Cache Capacity", "Cache Used", "Cache Remaining"):
        m = re.search(r"^" + k + r": (\d+)", r.stdout, re.M)
        d[k] = int(m.group(1)) if m else None
    return d


def count(fn, off, pat):
    with open(fn, "rb") as f:
        f.seek(off)
        return f.read().decode("utf-8", "replace").count(pat)


rows = []
w = open(out, "w", newline="")
cw = csv.writer(w)
cw.writerow(["phase", "t_s", "VmLck_kB", "VmLck_delta_kB", "CacheCapacity", "CacheUsed", "NumBlocksCached",
             "NumBlocksFailedToCache", "BYTES_NEEDED", "BYTES_CACHED", "FILES_CACHED",
             "NN_CacheCapacity", "NN_CacheUsed", "NN_CacheRemaining"])
settled = False
while True:
    ts = time.time()
    v = vmlck(); cc, cu, nb, nf = jmx(); ds = dstats(); rp = report()
    el = ts - t0
    row = [phase, round(el, 1), v, v - base, cc, cu, nb, nf, ds.get("BYTES_NEEDED"), ds.get("BYTES_CACHED"),
           ds.get("FILES_CACHED"), rp["Configured Cache Capacity"], rp["Cache Used"], rp["Cache Remaining"]]
    rows.append(row); cw.writerow(row); w.flush()
    key = lambda r: (r[5], r[6], r[7], r[2], r[9])
    if el >= 60 and len(rows) >= 4 and len({key(r) for r in rows[-4:]}) == 1:
        settled = True
        break
    if el >= 120:
        break
    time.sleep(max(0.0, 5.0 - (time.time() - ts)))
w.close()
L = rows[-1]
print(f"CLCHK,{phase},C={C},path={path},settled={settled},t={L[1]},samples={len(rows)},"
      f"VmLck_kB={L[2]},VmLckDelta_kB={L[3]},CacheCapacity={L[4]},CacheUsed={L[5]},NumBlocksCached={L[6]},"
      f"NumBlocksFailedToCache={L[7]},BYTES_NEEDED={L[8]},BYTES_CACHED={L[9]},FILES_CACHED={L[10]},"
      f"NN_CacheUsed={L[12]},NN_CacheRemaining={L[13]},"
      f"maxCacheUsed={max(r[5] for r in rows)},maxVmLckDelta_kB={max(r[3] for r in rows)},"
      f"maxNumBlocksCached={max(r[6] for r in rows)},"
      f"nnRejectLines={count(nnlog, nnoff, REJ)},nnAddedLines={count(nnlog, nnoff, ADD)},"
      f"nnInsufficientLines={count(nnlog, nnoff, INS)},dnCouldNotReserveLines={count(dnlog, dnoff, NORES)},"
      f"withinCap={max(r[5] for r in rows) <= C and max(r[3] for r in rows) <= C // 1024 + 16}")
