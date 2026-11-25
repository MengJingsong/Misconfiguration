#!/usr/bin/env python3
"""Self-check for order 31: recompute the deciding readings from run1/ raw files (not from CLCHK/summary lines).
Usage: python3 -I selfcheck.py <o31-dir>"""
import csv, re, sys, os
d = sys.argv[1]
B = 16777216
print("== unit (run1/unit/o31-lines.txt)")
rows = {}
for line in open(os.path.join(d, "run1/unit/o31-lines.txt")):
    parts = line.strip().split(",")
    tag = parts[1]
    kv = dict(p.split("=", 1) for p in parts[2:] if "=" in p)
    if tag == "U1":
        mv = re.search(r"max available space is (\d+), but (\d+)is required", line)
        ok = int(kv["reserves"]); used = int(kv["cacheUsed"])
        upv = [int(x) for x in kv["usedPerVol"].split("/")]; mpv = [int(x) for x in kv["maxPerVol"].split("/")]
        print(f"U1 M={kv['M']} B={kv['B']}: reserves={ok} used={used} keys={kv['keysPerVol']} usedPerVol={upv} max={mpv} "
              f"over={any(u > m for u, m in zip(upv, mpv))} refusal maxAvail={mv.group(1)}")
    elif tag == "U1REAL":
        print(f"U1REAL cap={kv['cacheCapacity']} sum={kv['sumUsable']} diff={int(kv['cacheCapacity'])-int(kv['sumUsable'])}")
    elif tag == "U2":
        rows[parts[2]] = kv
    elif tag.startswith("U3"):
        print(tag, {k: kv[k] for k in kv if k != "path"})
polls = {}
for line in open(os.path.join(d, "run1/unit/o31-lines.txt")):
    if line.startswith("O31,U2POLL,"):
        p = line.strip().split(","); kv = dict(x.split("=", 1) for x in p[3:])
        polls.setdefault(p[2], []).append(kv)
for tag, kv in rows.items():
    pl = polls[tag]
    print(f"U2 {tag}: settled={kv['settled']} numBlocksCached={kv['numBlocksCached']} cacheUsed={kv['cacheUsed']} "
          f"maxUsedPolls={max(int(x['cacheUsed']) for x in pl)} fileBytes={kv['fileBytes']} max={kv['maxPerVol']} "
          f"refusalLines={kv['refusalLines']} values={kv['refusalValues']} couldNot={kv['couldNotReserveLines']} "
          f"failed={kv['numBlocksFailedToCache']} lastPollRefusals={pl[-1]['refusals']} polls={len(pl)} lastT={pl[-1]['t']}")
ex = open(os.path.join(d, "run1/unit/unit-log-excerpt.txt")).read()
print("unit log: refusal lines", ex.count("There is no enough persistent memory space"),
      "values", sorted(set(re.findall(r"max available space is (\d+)", ex))),
      "| loader lines", len(re.findall(r"Initializing cache loader: \S+PmemMappableBlockLoader", ex)),
      "| WARN null", ex.count("Failed to delete the mapped File: null"))
print("== cluster (run1/cluster/samples-*.csv, files-*.txt, dn-excerpt-*.txt)")
for k in ["K1", "K2", "K3", "K4", "K5"]:
    r = list(csv.DictReader(open(os.path.join(d, f"run1/cluster/samples-{k}.csv"))))
    last = r[-1]
    files = [l.split() for l in open(os.path.join(d, f"run1/cluster/files-{k}.txt"))]
    per = {}
    for size, path in files:
        if "/hdfs_pmem_cache/" in path:
            v = path.split("/cluster/")[1].split("/")[0]
            per.setdefault(v, [0, 0]); per[v][0] += 1; per[v][1] += int(size)
    ex = open(os.path.join(d, f"run1/cluster/dn-excerpt-{k}.txt")).read()
    added = [int(x) for x in re.findall(r"Added persistent memory - \S+ with size=(\d+)", ex)]
    vals = sorted(set(re.findall(r"max available space is (\d+)", ex)))
    print(f"{k}: samples={len(r)} lastT={last['t']} maxBytes(log)={added} CacheCapacity={last['CacheCapacity']} "
          f"CacheUsed={last['CacheUsed']} NumBlocksCached={last['NumBlocksCached']} maxCacheUsed={max(int(x['CacheUsed']) for x in r)} "
          f"maxDu0={max(int(x['du0']) for x in r)} maxDu1={max(int(x['du1']) for x in r)} minAvail0={min(int(x['dfavail0']) for x in r)} "
          f"cacheFiles={per} blocks={sum(v[0] for v in per.values())} "
          f"refusals={ex.count('There is no enough persistent memory space')} values={vals} "
          f"couldNot={ex.count('could not reserve')} loadFail={ex.count('Failed to cache the block')} "
          f"checksumEOF={ex.count('checksum verification failed: premature EOF')} ok={ex.count('Successfully cached one replica')} "
          f"loader={'PmemMappableBlockLoader' in ex}")
    # per-volume overshoot check: files bytes vs log maxBytes
    for i, v in enumerate(sorted(per)):
        if i < len(added):
            print(f"   {v}: file bytes {per[v][1]} <= maxBytes {added[i]}: {per[v][1] <= added[i]}; blocks={per[v][1]//B}")
