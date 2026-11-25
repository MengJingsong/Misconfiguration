#!/usr/bin/env python3
"""Order 28 cluster tier: check B3f (as amended D1-6, D1-7) against run1/cluster/readings.csv.
Usage: python3 -I analyze-cluster.py <readings.csv>   (T and R values are read from the CSV and constants below)"""
import csv, sys

MIB = 1048576
NEED = 15 * MIB
S = MIB + 8 * 1024          # per-append on-disk growth (B3c)
T = 2110627840              # df size of the cluster image (cluster-run.log CALIB line)

rows = list(csv.DictReader(open(sys.argv[1])))
for r in rows:
    for k in r:
        if k not in ("label", "file", "t0", "t1"):
            r[k] = int(r[k])

def show(label):
    return [r for r in rows if r["label"] == label]

print("== boundary and control")
for lab in ("bM4M", "bP4M", "ctrlR0"):
    for r in show(lab):
        print(f"{lab} {r['file']} rc={r['rc']} R={r['R']} freeSpace_before={r['free_before']} "
              f"(< B-L: {r['free_before'] < NEED}) du_before={r['du_before']} du_after={r['du_after']} "
              f"du_delta={r['du_after'] - r['du_before']} used_delta={r['used_after'] - r['used_before']} "
              f"insufficient_lines={r['insufficient_lines']} attempts={r['append_attempts']}")

print("== gate check over every append: refused == (freeSpace_before < B-L)")
bad = [r for r in rows if (r["rc"] != 0) != (r["free_before"] < NEED)]
print(f"appends={len(rows)} mismatches={len(bad)}")
for r in bad:
    print("  MISMATCH", r)
print("refusals with no Insufficient line:", sum(1 for r in rows if r["rc"] != 0 and r["insufficient_lines"] < 1))
print("successes with an Insufficient line:", sum(1 for r in rows if r["rc"] == 0 and r["insufficient_lines"] > 0))
print("append attempts per append (DN 'Appending to'):", sorted(set(r["append_attempts"] for r in rows)))

stops = {}
for lab, a in (("fill48", 48 * MIB), ("fill80", 80 * MIB)):
    rs = show(lab)
    ok = [r for r in rs if r["rc"] == 0]
    fail = [r for r in rs if r["rc"] != 0]
    R = rs[0]["R"]
    npred = (a - NEED) // S + 1
    print(f"== {lab}: R_F={R} a={a} start freeSpace={rs[0]['free_before']} successes={len(ok)} "
          f"(pred {npred} +-2) refusals={len(fail)} first refusal at {fail[0]['file'] if fail else None}")
    if not fail:
        continue
    f = fail[0]
    lo, hi = T - R - 16 * MIB, T - R - 14 * MIB
    print(f"  stop freeSpace={f['free_before']} in [15MiB-s, 15MiB)=[{NEED - S},{NEED}): {NEED - S <= f['free_before'] < NEED}")
    print(f"  du -sb dn at stop={f['du_after']} (before={f['du_before']}) in [T-R-16MiB, T-R-14MiB]=[{lo},{hi}]: {lo <= f['du_after'] <= hi}")
    print(f"  max du -sb dn during fill={max(r['du_after'] for r in rs)} <= T-R={T - R}: {max(r['du_after'] for r in rs) <= T - R}")
    nondfs = f["df_used"] - f["du_after"]
    print(f"  df avail at stop={f['df_avail']} >= R-nonDfs={R - nondfs}: {f['df_avail'] >= R - nondfs}  (nonDfs={nondfs})")
    print(f"  Insufficient lines at the refusal={f['insufficient_lines']}  freeSpace before each success min={min(r['free_before'] for r in ok)}")
    steps = [rs[i]["free_before"] - rs[i + 1]["free_before"] for i in range(len(rs) - 1)]
    print(f"  freeSpace step per append (before-to-before): min={min(steps)} max={max(steps)} set={sorted(set(steps))}")
    dsteps = [r["du_after"] - r["du_before"] for r in ok]
    print(f"  du -sb growth per successful append: {sorted(set(dsteps))}")
    stops[lab] = (R, f["du_after"])
if len(stops) == 2:
    (r48, d48), (r80, d80) = stops["fill48"], stops["fill80"]
    print(f"== D1-7: du at stop80 - du at stop48 = {d80 - d48}; R_F(48)-R_F(80) = {r48 - r80}; "
          f"diff = {d80 - d48 - (r48 - r80)} (|.| <= 2 MiB: {abs(d80 - d48 - (r48 - r80)) <= 2 * MIB})")
