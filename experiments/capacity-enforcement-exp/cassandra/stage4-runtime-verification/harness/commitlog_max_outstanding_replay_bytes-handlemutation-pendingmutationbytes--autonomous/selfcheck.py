#!/usr/bin/env python3
"""Self-check for case o32: re-derives the numbers the conclusion cites, with parsing independent of the analyzers.
Usage: selfcheck.py <unit-session-excerpt.txt> <cluster dir on the node, or a copy with */samples.jsonl, */system.log, */session.txt>
Unit: parses the log-format O32 lines (not unit-o32.txt). Cluster: takes samples by the sampler's own
'complete_after' flag (not by log timestamps), reads N from the raw system.log, and the -D values from the
JVM command line echoed in session.txt; also counts ERROR lines and OutOfMemory mentions."""
import glob, os, re, sys
ex, cdir = sys.argv[1], sys.argv[2]
print("== unit ==")
for line in open(ex):
    if "O32 LIMIT=" in line:
        kv = dict(re.findall(r"(\w+)=(\d+)", line.split("O32 ", 1)[1]))
        L, p, q, s, c = (int(kv[k]) for k in ("LIMIT", "peakPending", "maxQueued", "s", "calls"))
        print(f"L={L} peak={p} peak-L={p-L} (s={s}; in (L-s, L+s]: {L-s < p <= L+s}) maxQueued={q} floor(L/s)+1={L//s+1} L/s={L/s:.1f} calls={c} callsOther={kv['callsOther']}")
print("== cluster ==")
for d in sorted(glob.glob(os.path.join(cdir, "*", "samples.jsonl"))):
    lab = os.path.basename(os.path.dirname(d))
    txt = open(d).read()
    recs = [l for l in txt.splitlines() if '"mut_n"' in l and '"complete_after": false' in l]
    muts = [int(re.search(r'"mut_n": (\d+)', l).group(1)) for l in recs]
    pus = [int(re.search(r'"pu_n": (\d+)', l).group(1)) for l in recs]
    used = [int(m.group(1)) * 1024 for l in recs for m in [re.search(r'"heap_used_k": (\d+)', l)] if m]
    tot = [int(m.group(1)) for l in recs for m in [re.search(r'"total_b": (\d+)', l)] if m]
    sl = open(os.path.join(os.path.dirname(d), "system.log"), errors="replace").read()
    m = re.search(r"Log replay complete, (\d+) replayed mutations in (\d+) ms", sl)
    errs = len(re.findall(r"(?m)^ERROR", sl)); oom = sl.count("OutOfMemoryError")
    ses = open(os.path.join(os.path.dirname(d), "session.txt"), errors="replace").read()
    dv = sorted(set(re.findall(r"commitlog_max_outstanding_replay_(bytes|count)=(\d+)", ses)))
    print(f"{lab}: samples={len(recs)} maxMutation={max(muts)} maxPU={max(pus)} nonzero_samples={sum(1 for x in muts if x)} "
          f"maxUsed={max(used)} maxHistTotal={max(tot)} N={m.group(1) if m else None} ms={m.group(2) if m else None} "
          f"ERROR={errs} OOM={oom} D={dv}")
