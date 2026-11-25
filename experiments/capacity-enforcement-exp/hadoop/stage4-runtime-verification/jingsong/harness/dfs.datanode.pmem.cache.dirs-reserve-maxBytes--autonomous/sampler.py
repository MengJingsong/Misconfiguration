#!/usr/bin/env python3
"""Stage-4 cluster sampler (B3d + S6) for dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous.
Every 2 s for <secs> s: DataNode JMX FSDatasetState (CacheCapacity, CacheUsed, NumBlocksCached, NumBlocksFailedToCache),
cache bytes = sum of regular-file sizes under the pmem mount (find -type f -printf %s), file count,
du -sb --apparent-size, df -B1 Used/Size, and counts of new NameNode/DataNode log lines since the given offsets.
Usage: sampler.py <phase> <pmemdir|-> <secs> <nnlog> <nnoff> <dnlog> <dnoff> <out.csv>"""
import csv
import json
import subprocess
import sys
import time
import urllib.request

phase, pmem, secs, nnlog, nnoff, dnlog, dnoff, out = sys.argv[1:9]
secs, nnoff, dnoff = float(secs), int(nnoff), int(dnoff)
PAT_NN = {"nnReject": b"is not a valid possibility because the block has size",
          "nnAdded": b"added to PENDING_CACHED on DataNode"}
PAT_DN = {"couldNotReserve": b"could not reserve more bytes",
          "noEnoughPmem": b"There is no enough persistent memory space",
          "failedToCacheBlock": b"Failed to cache the block",
          "noSpaceLeft": b"No space left on device",
          "prematureEOF": b"premature EOF",
          "checksumFailed": b"checksum verification failed",
          "cachedReplica": b"Successfully cached one replica",
          "uncachedReplica": b"Successfully uncached one replica"}


def jmx():
    try:
        with urllib.request.urlopen(
                "http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*", timeout=5) as r:
            beans = json.load(r)["beans"]
        b = [x for x in beans if "FSDatasetState-" in x.get("name", "")] or beans
        b = b[0]
        return [b.get("CacheCapacity"), b.get("CacheUsed"), b.get("NumBlocksCached"), b.get("NumBlocksFailedToCache")]
    except Exception as e:  # noqa
        return ["err", "err", "err", "err"]


def sh(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False).stdout.decode()
    except Exception:  # noqa
        return ""


def disk():
    if pmem == "-":
        return [0, 0, 0, 0, 0]
    sizes = [int(x) for x in sh(["find", pmem, "-type", "f", "-printf", "%s\n"]).split()]
    du = sh(["du", "-sb", "--apparent-size", pmem]).split()
    df = sh(["df", "-B1", "--output=used,size", pmem]).split()
    return [sum(sizes), len(sizes), int(du[0]) if du else -1,
            int(df[2]) if len(df) >= 4 else -1, int(df[3]) if len(df) >= 4 else -1]


def counts(path, off, pats):
    try:
        with open(path, "rb") as f:
            f.seek(off)
            data = f.read()
    except Exception:  # noqa
        data = b""
    return [data.count(p) for p in pats.values()]


hdr = (["phase", "t_s", "CacheCapacity", "CacheUsed", "NumBlocksCached", "NumBlocksFailedToCache",
        "cacheFileBytes", "cacheFiles", "duApparent", "dfUsed", "dfSize"] + list(PAT_NN) + list(PAT_DN))
t0 = time.time()
rows = []
with open(out, "w", newline="") as fo:
    w = csv.writer(fo)
    w.writerow(hdr)
    while True:
        t = time.time() - t0
        row = ([phase, "%.1f" % t] + jmx() + disk() + counts(nnlog, nnoff, PAT_NN) + counts(dnlog, dnoff, PAT_DN))
        w.writerow(row)
        fo.flush()
        rows.append(row)
        if t >= secs:
            break
        time.sleep(max(0.0, 2.0 - ((time.time() - t0) - t)))


def mx(i):
    v = [r[i] for r in rows if isinstance(r[i], int)]
    return max(v) if v else "na"


last = rows[-1]
print("SAMPLES phase=%s n=%d last=%s" % (phase, len(rows), dict(zip(hdr[1:], last[1:]))))
print("MAX phase=%s maxCacheUsed=%s maxCacheFileBytes=%s maxCacheFiles=%s maxDfUsed=%s maxNumBlocksCached=%s" % (
    phase, mx(3), mx(6), mx(7), mx(9), mx(4)))
