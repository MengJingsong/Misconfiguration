#!/usr/bin/env python3
"""Cluster-tier sampler (B3d + A6) for CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous.

usage: sampler.py <phase> <pool> <limit> <change_epoch> <nnlog> <nnlog_offset> <dnpid> <vmlck_base_kB> <csv>
Samples every 2 s: DataNode VmLck, DataNode JMX (CacheUsed, NumBlocksCached, CacheCapacity) and
`hdfs cacheadmin -listPools -stats <pool>`. Plateau: last 10 samples of (CacheUsed, NumBlocksCached,
VmLck, BYTES_CACHED) equal, at least 60 s after the change; at most 120 s, else settled=false.
Prints one CLCHK line with the plateau reading and the "not scanning file" names in the NameNode log.
"""
import csv, json, re, subprocess, sys, time, urllib.request

phase, pool, limit, t0, nnlog, off0, dnpid, base, out = sys.argv[1:10]
t0 = float(t0); off0 = int(off0); base = int(base)
SKIP = re.compile(r"not scanning file (\S+) because")


def vmlck():
    with open(f"/proc/{dnpid}/status") as f:
        for line in f:
            if line.startswith("VmLck:"):
                return int(line.split()[1])
    return -1


def jmx():
    u = "http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*"
    d = json.load(urllib.request.urlopen(u, timeout=10))
    b = d["beans"][0]
    return b["CacheUsed"], b["NumBlocksCached"], b["CacheCapacity"]


def poolstats():
    r = subprocess.run(["hdfs", "cacheadmin", "-listPools", "-stats", pool],
                       capture_output=True, text=True, timeout=60)
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    hdr = None
    for l in lines:
        f = l.split()
        if f and f[0] == "NAME":
            hdr = f
        elif hdr and f and f[0] == pool:
            return dict(zip(hdr, f))
    return {}


def logsize():
    import os
    return os.path.getsize(nnlog)


def names(a, b):
    with open(nnlog, "rb") as f:
        f.seek(a)
        txt = f.read(max(0, b - a)).decode("utf-8", "replace")
    return sorted(set(SKIP.findall(txt))), len(SKIP.findall(txt))


rows = []
w = open(out, "w", newline="")
cw = csv.writer(w)
cw.writerow(["phase", "t_s", "VmLck_kB", "VmLck_delta_kB", "CacheUsed", "NumBlocksCached", "CacheCapacity",
             "LIMIT", "BYTES_NEEDED", "BYTES_CACHED", "BYTES_OVERLIMIT", "FILES_NEEDED", "FILES_CACHED", "nnlog_size"])
settled = False
while True:
    ts = time.time()
    v = vmlck(); cu, nb, cc = jmx(); ps = poolstats(); ls = logsize()
    el = ts - t0
    row = [phase, round(el, 1), v, v - base, cu, nb, cc, ps.get("LIMIT"), ps.get("BYTES_NEEDED"),
           ps.get("BYTES_CACHED"), ps.get("BYTES_OVERLIMIT"), ps.get("FILES_NEEDED"), ps.get("FILES_CACHED"), ls]
    rows.append(row); cw.writerow(row); w.flush()
    key = lambda r: (r[4], r[5], r[2], r[9])
    if el >= 60 and len(rows) >= 10 and len({key(r) for r in rows[-10:]}) == 1:
        settled = True
        break
    if el >= 120:
        break
    time.sleep(max(0.0, 2.0 - (time.time() - ts)))
w.close()
last = rows[-1]
win, nwin = names(rows[-10][13] if len(rows) >= 10 else off0, logsize())
since, nsince = names(off0, logsize())
print(f"CLCHK,{phase},pool={pool},L={limit},settled={settled},t={last[1]},samples={len(rows)},"
      f"VmLck_kB={last[2]},VmLckDelta_kB={last[3]},CacheUsed={last[4]},NumBlocksCached={last[5]},"
      f"CacheCapacity={last[6]},LIMIT={last[7]},BYTES_NEEDED={last[8]},BYTES_CACHED={last[9]},"
      f"BYTES_OVERLIMIT={last[10]},FILES_NEEDED={last[11]},FILES_CACHED={last[12]},"
      f"maxCacheUsed={max(r[4] for r in rows)},maxVmLckDelta_kB={max(r[3] for r in rows)},"
      f"skipWindow={';'.join(win) or '-'},skipWindowLines={nwin},skipSince={';'.join(since) or '-'},skipSinceLines={nsince}")
