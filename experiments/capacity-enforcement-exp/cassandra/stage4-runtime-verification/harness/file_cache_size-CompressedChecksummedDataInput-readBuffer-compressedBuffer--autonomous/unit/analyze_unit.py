#!/usr/bin/env python3
"""analyze_unit.py <outdir> : parse cells/*.log OBS lines -> table + checks. Re-parses raw logs only."""
import sys, re, glob, os, json
out = sys.argv[1]
MiB = 1 << 20
def parse(path):
    d = {}
    for l in open(path, errors="replace"):
        m = re.search(r"OBS (\w+) (.*)$", l)
        if not m: continue
        lab, rest = m.groups()
        kv = dict(re.findall(r"(\w+)=(-?\d+|\S+)", rest))
        for k, v in list(kv.items()):
            if re.fullmatch(r"-?\d+", v): kv[k] = int(v)
        d.setdefault(lab, kv)
        if lab == "parked" and "hintsRead" in rest and "hintsRead" not in d["parked"]: d["parked"].update(kv)
    d["_exit"] = "exit=0" in open(path, errors="replace").read()
    return d
rows = []
for p in sorted(glob.glob(f"{out}/cells/*.log")):
    cell = os.path.basename(p)[:-4]
    d = parse(p); d["cell"] = cell
    rows.append(d)
res = []
print("## readers (LZ4/Deflate)")
print("cell | thr MiB | B | R | hints read/exp | fail | d_overflow | exp_overflow(R*(2.1B-4096)) | ratio | d_pooled | d_direct | d_heap | resid_overflow(closed) | exp_resid(R*(1.05B-4096)) | d_direct_closed | d_inuse_pooled(parked) | d_inuse_pooled(closed)")
for d in rows:
    if "parked" not in d: continue
    c = d["config"]; B, R, thr = c["B"], c["R"], c["threshold"]
    b, pk, cl = d["baseline"], d["parked"], d["closed"]
    do = pk["overflow"] - b["overflow"]; dp = pk["pooled"] - b["pooled"]; dd = pk["direct"] - b["direct"]; dh = pk["heap"] - b["heap"]
    ro = cl["overflow"] - b["overflow"]; ddc = cl["direct"] - b["direct"]
    eo = R * (2 * 1.05 * B - 4096); er = R * (1.05 * B - 4096)
    dup = (pk["used"] - pk["overflow"]) - (b["used"] - b["overflow"]); dupc = (cl["used"] - cl["overflow"]) - (b["used"] - b["overflow"])
    print(f"{d['cell']} | {thr//MiB} | {B} | {R} | {pk.get('hintsRead')}/{pk.get('expected')} | {pk.get('failures')} | {do} | {int(eo)} | {do/eo:.3f} | {dp} | {dd} | {dh} | {ro} | {int(er)} | {ddc} | {dup} | {dupc}")
print("\n## controls")
for d in rows:
    if d.get("config",{}).get("mode") != "control": continue
    thr = d["config"]["threshold"]
    print(d["cell"], "baseline pooled/over", d["baseline"]["pooled"], d["baseline"]["overflow"], "| at1x pooled/over", d["control_at_1x"]["pooled"], d["control_at_1x"]["overflow"], "| at3x pooled/over", d["control_at_3x"]["pooled"], d["control_at_3x"]["overflow"], "| expect pooled", (thr//(8*MiB))*8*MiB, "| released pooled/over/used", d["control_released"]["pooled"], d["control_released"]["overflow"], d["control_released"]["used"])
print("\n## cells not done:", [d["cell"] for d in rows if "done" not in d and not d["_exit"]])
