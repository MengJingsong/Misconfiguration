#!/usr/bin/env python3
"""Cluster tier (B3f/B3g) of case o32. Usage: cluster-analyze.py <cluster dir with b16m b64m b256m b4g c16>
Operationalisation fixed before the cluster readings were looked at (results section 4):
  s = 65,600 bytes (B3f); 'small slack' = 10 Mutation instances (the reader's current mutation, the rebuilt
  Mutation of each of the 2 appliers, a few system mutations); 'count ~ L/s' for the confirmed row = max count in
  [0.5 L/s, L/s + 1 + 10]; count-cap control: max count <= 17 + 10; 'N ~ 24,000': N >= 23,500;
  'limit never reached' (B3g row 3): the 4 GiB run's max count < 257.
Samples used: those whose jcmd started before the 'Log replay complete' log line (epoch ms from the log, UTC)."""
import json, os, re, sys, datetime
D = sys.argv[1]
S = 65600; SLACK = 10
RUNS = [("b16m", 16777216), ("b64m", 67108864), ("b256m", 268435456), ("b4g", 4294967296), ("c16", None)]
def logms(line):
    m = re.search(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3})", line)
    dt = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000) + int(m.group(2))
res = {}
for lab, L in RUNS:
    d = os.path.join(D, lab)
    if not os.path.exists(os.path.join(d, "samples.jsonl")):
        print(f"{lab}: missing"); continue
    syslog = open(os.path.join(d, "system.log"), errors="replace").read().splitlines()
    rep = [l for l in syslog if "Replaying " in l and "CommitLog.java" in l]
    done = [l for l in syslog if "Log replay complete" in l]
    t_start = logms(rep[0]) if rep else None
    t_done = logms(done[0]) if done else None
    m = re.search(r"Log replay complete, (\d+) replayed mutations in (\d+) ms", done[0]) if done else None
    N, ms = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    smp = [json.loads(l) for l in open(os.path.join(d, "samples.jsonl"))]
    smp = [x for x in smp if "event" not in x and x.get("ok")]
    inrep = [x for x in smp if t_done is None or x["t_ms"] < t_done]
    during = [x for x in inrep if t_start is not None and x["t1_ms"] >= t_start]
    mx = max((x["mut_n"] for x in inrep), default=None)
    mxpu = max((x["pu_n"] for x in inrep), default=None)
    mxused = max((x.get("heap_used_k", 0) * 1024 for x in inrep), default=None)
    mxlive = max((x.get("total_b", 0) for x in inrep), default=None)
    opts = open(os.path.join(d, "session.txt"), errors="replace").read()
    cnt = re.findall(r"-Dcassandra\.commitlog_max_outstanding_replay_(bytes|count)=(\d+)", opts)
    res[lab] = dict(L=L, N=N, ms=ms, samples=len(inrep), during=len(during), max_mut=mx, max_pu=mxpu, max_used=mxused, max_live=mxlive,
                    series=[x["mut_n"] for x in inrep], opts=sorted(set(cnt)))
    print(f"{lab}: L={L} N={N} replay_ms={ms} samples_before_complete={len(inrep)} (after 'Replaying': {len(during)}) "
          f"max_Mutation={mx} max_PartitionUpdate={mxpu} max_heap_used={mxused} max_hist_total={mxlive} opts={sorted(set(cnt))}")
    print(f"   Mutation series: {res[lab]['series']}")
ok = True
def exp(name, cond, detail):
    global ok
    ok &= bool(cond); print(f"EXPECTED: {name}: {'PASS' if cond else 'FAIL'} ({detail})")
fin = [l for l, L in RUNS if L and L < 4294967296 and l in res]
over = []; reached = True
for l in fin:
    L = res[l]["L"]; c = res[l]["max_mut"]; b = L / S
    exp(f"{l} max Mutation <= L/s+1+{SLACK}", c is not None and c <= b + 1 + SLACK, f"max={c} L/s={b:.1f}")
    if c is not None and c > b + 1 + SLACK: over.append(l)
    exp(f"{l} max Mutation >= 0.5 L/s (limit reached)", c is not None and c >= 0.5 * b, f"max={c} 0.5L/s={0.5*b:.1f}")
    if c is None or c < 0.5 * b: reached = False
if "b4g" in res and "b256m" in res:
    exp("b4g max Mutation >= 4 x b256m", res["b4g"]["max_mut"] >= 4 * res["b256m"]["max_mut"], f"{res['b4g']['max_mut']} vs 4x{res['b256m']['max_mut']}")
    exp("b4g max used > b256m max used", res["b4g"]["max_used"] > res["b256m"]["max_used"], f"{res['b4g']['max_used']} vs {res['b256m']['max_used']}")
if "b256m" in res and "b16m" in res:
    dlt = res["b256m"]["max_used"] - res["b16m"]["max_used"]
    exp("b256m max used >= b16m + 200 MB", dlt >= 200_000_000, f"delta={dlt}")
if "c16" in res:
    exp("c16 max Mutation <= 17+10", res["c16"]["max_mut"] <= 27, f"max={res['c16']['max_mut']}")
for l in res:
    exp(f"{l} N >= 23500", (res[l]["N"] or 0) >= 23500, f"N={res[l]['N']}")
void = [l for l in res if (res[l]["N"] or 0) < 23500]
if void: print(f"MATCHED: B3g row 5 (N replayed << 24,000 in {void}): result void")
elif "c16" in res and res["c16"]["max_mut"] > 27: print("MATCHED: B3g row 4 (count-cap control failed): result void")
elif over: print(f"MATCHED: B3g row 2 (count above L/s + slack in {over}): claim wrong")
elif "b4g" in res and res["b4g"]["max_mut"] < 257: print("MATCHED: B3g row 3 (limit never reached): not confirmed")
elif ok: print("MATCHED: B3g row 1 (claim confirmed)")
else: print("MATCHED: none -> Not confirmed (no matching row)")
