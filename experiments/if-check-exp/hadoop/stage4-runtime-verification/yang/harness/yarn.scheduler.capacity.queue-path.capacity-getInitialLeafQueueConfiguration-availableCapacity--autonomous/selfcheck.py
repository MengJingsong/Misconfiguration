#!/usr/bin/env python3
"""Self-check (results §5) for
yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity--autonomous

Usage: python3 -I selfcheck.py <run-dir>
Re-parses the RAW files, independently of unit-run.sh / cluster-run.py summaries:
  unit:    logs/unit/rep{1,2,3}/*TestIfCheck*-output.txt (surefire output), surefire report counts
  cluster: logs/cluster/run-C*.tsv (raw 2-s samples), cluster-run.log (window start times),
           apps-C*.json and scheduler-C*-end.json (REST snapshots), the ResourceManager log
           (policy DEBUG lines with availableCapacity), the NodeManager log (pmem kills), client logs.
Prints each check with PASS/FAIL against the frozen B2f/B3f values.
"""
import glob, json, os, re, statistics, sys
from datetime import datetime, timedelta

RUN = sys.argv[1]
L = f"{RUN}/logs"
fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    if not ok:
        fails.append(name)


# ---------------- unit tier ----------------
print("== unit tier (B2f, frozen)")
EXP_CREATE = {
    "U1": [("u1", .201, .1, True, .1, 102400), ("u2", .101, .1, True, .2, 102400), ("u3", .001, 0, False, .2, 102400)],
    "U2": [("u1", .201, .05, True, .05, 102400), ("u2", .151, .05, True, .1, 102400), ("u3", .101, .05, True, .15, 102400),
           ("u4", .051, .05, True, .2, 102400), ("u5", .001, 0, False, .2, 102400)],
    "U3": [("u1", .401, .2, True, .2, 102400), ("u2", .201, .2, True, .4, 102400), ("u3", .001, 0, False, .4, 102400)],
    "U4": [("u1", .201, .1, True, .1, 25600), ("u2", .101, .1, True, .2, 25600), ("u3", .001, 0, False, .2, 25600)],
}
reps = {}
for rep in (1, 2, 3):
    outs = glob.glob(f"{L}/unit/rep{rep}/*TestIfCheck*-output.txt")
    rpt = glob.glob(f"{L}/unit/rep{rep}/*TestIfCheck*.txt")
    rpt = [r for r in rpt if not r.endswith("-output.txt")]
    lines = [l.rstrip("\n") for l in open(outs[0], errors="replace") if l.startswith("IFCHK\t")]
    reps[rep] = lines
    summary = open(rpt[0]).read()
    check(f"unit rep{rep} surefire 4 run, 0 failures, 0 errors",
          "Tests run: 4, Failures: 0, Errors: 0, Skipped: 0" in summary)
check("unit repeats identical (all IFCHK lines)", reps[1] == reps[2] == reps[3],
      f"{len(reps[1])}/{len(reps[2])}/{len(reps[3])} lines")


def kv(fields):
    return {f.split("=", 1)[0]: f.split("=", 1)[1] for f in fields if "=" in f}


lines = reps[1]
used80 = {}
for rid, exp in EXP_CREATE.items():
    cr = [l.split("\t") for l in lines if l.split("\t")[1] == rid and l.split("\t")[2] == "create"]
    for (u, av, ac, act, sm, em), f in zip(exp, cr):
        d = kv(f[4:])
        ok = (f[3] == u and abs(float(d["avail"]) - av) < 5e-4 and abs(float(d["leafAbsCap"]) - ac) < 5e-4
              and (d["active"] == "true") == act and abs(float(d["actSum"]) - sm) < 5e-4 and int(d["effMaxMB"]) == em)
        check(f"unit {rid} create {u}", ok, "\t".join(f[3:]))
    us = {}
    for l in lines:
        f = l.split("\t")
        if f[1] == rid and f[2] == "usage" and f[3] == "hb=80":
            us[f[4]] = int(kv(f[5:])["usedMB"])
    used80[rid] = us
    end = [l for l in lines if l.split("\t")[1] == rid and l.split("\t")[2] == "end"]
    print(f"      {rid} hb=80 used: {us} | end: {end[0].split(chr(9))[3:] if end else None}")
    check(f"unit {rid} u3 app RUNNING at end", bool(end) and "u3AppState=RUNNING" in end[0])
    check(f"unit {rid} u1,u2 used 1024", us.get("u1") == 1024 and us.get("u2") == 1024)
for rid in ("U1", "U2", "U3"):
    check(f"unit {rid} u3 used ~41984 (+-1024)", abs(used80[rid]["u3"] - 41984) <= 1024, str(used80[rid]["u3"]))
check("unit |U1-U2|<=1024 and |U3-U2|<=1024 (u3)",
      abs(used80["U1"]["u3"] - used80["U2"]["u3"]) <= 1024 and abs(used80["U3"]["u3"] - used80["U2"]["u3"]) <= 1024)
u4 = used80["U4"]["u3"]
check("unit U4 control u3 <= 26624 and >=15 unsatisfied", u4 <= 26624 and 40 - (u4 - 1024) // 1024 >= 15,
      f"used={u4} unsatisfied={40 - (u4 - 1024) // 1024}")

# ---------------- cluster tier ----------------
print("== cluster tier (B3f, frozen)")
clog = open(f"{L}/cluster/cluster-run.log").read()
wstarts = [datetime.strptime(m, "%Y-%m-%d %H:%M:%S") for m in
           re.findall(r"\[(\S+ \S+)\] window start:", clog)]
check("cluster 4 windows logged", len(wstarts) == 4, str([str(w) for w in wstarts]))
rmlog = glob.glob(f"{L}/*resourcemanager*.log")[0]
pol = []
for l in open(rmlog, errors="replace"):
    m = re.match(r"(\S+ \S+),\d+ DEBUG .*GuaranteedOrZeroCapacityOverTimePolicy: Parent queue = root.parent, nodeLabel = , "
                 r"absCapacity = (\S+), leafQueueAbsoluteCapacity = (\S+), deactivatedCapacity = \S+, "
                 r"absChildActivatedCapacity = (\S+), availableCapacity = (\S+)", l)
    if m:
        pol.append((datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), *[float(x.rstrip(",")) for x in m.groups()[1:]]))
nmlog = glob.glob(f"{L}/*nodemanager*.log")[0]
pmem = sum(1 for l in open(nmlog, errors="replace") if "beyond physical memory" in l or "PHYSICAL memory" in l)
check("cluster NodeManager log: no pmem kills", pmem == 0, f"count={pmem}")

# run -> (u3 absCap %, u3 absMax %, parent abs, template abs, activated sum, availableCapacity)
EXP = {"C1": (0, 100, .2, .1, .2, .001), "C2": (5, 100, .2, .05, .15, .051), "C3": (0, 100, .4, .2, .4, .001), "C4": (0, 25, .2, .1, .2, .001)}
R = {}
for i, run in enumerate(("C1", "C2", "C3", "C4")):
    rows = [l.rstrip("\n").split("\t") for l in open(f"{L}/cluster/run-{run}.tsv")][1:]
    per = {}
    for u in ("u1", "u2", "u3"):
        rr = [r for r in rows if r[1] == f"root.parent.{u}"]
        per[u] = dict(n=len(rr), abs=sorted({float(r[2]) for r in rr}), absmax=sorted({float(r[3]) for r in rr}),
                      used=statistics.median(float(r[4]) for r in rr), usedmin=min(float(r[4]) for r in rr),
                      usedmax=max(float(r[4]) for r in rr), cnt=statistics.median(int(r[6]) for r in rr),
                      rss=statistics.median(float(r[7]) for r in rr), apps=sorted({r[5] for r in rr}))
    R[run] = per
    a3, am3 = EXP[run][0], EXP[run][1]
    print(f"      {run}: " + "; ".join(f"{u} n={p['n']} abs={p['abs']} max={p['absmax']} used={p['used']:.0f} "
                                       f"[{p['usedmin']:.0f},{p['usedmax']:.0f}] hog={p['cnt']} rss={p['rss']:.1f}"
                                       for u, p in per.items()))
    check(f"cluster {run} 61 samples per leaf", all(p["n"] == 61 for p in per.values()))
    check(f"cluster {run} u3 absoluteCapacity constant {a3}, absMax {am3}",
          per["u3"]["abs"] == [float(a3)] and per["u3"]["absmax"] == [float(am3)])
    check(f"cluster {run} u1,u2 2048 MB, 1 hog each",
          all(per[u]["used"] == 2048 and per[u]["usedmin"] == per[u]["usedmax"] and per[u]["cnt"] == 1 for u in ("u1", "u2")))
    # policy operand during the window (independent of REST): availableCapacity, activated sum
    w0 = wstarts[i]
    win = [p for p in pol if w0 <= p[0] <= w0 + timedelta(seconds=120)]  # the 120 s sampling window (B3c); the kills follow it
    vals = sorted({(p[1], p[2], p[3], round(p[4], 4)) for p in win})
    want = [tuple(EXP[run][2:6])]
    check(f"cluster {run} policy log in window (parentAbs, templateAbs, actSum, available) = {want[0]}",
          len(win) > 50 and vals == want, f"{len(win)} lines, values {vals}")
    apps = json.load(open(f"{L}/cluster/apps-{run}.json"))["apps"]["app"]
    by = {a["user"]: a for a in apps}
    order = by["u1"]["startedTime"] < by["u2"]["startedTime"] < by["u3"]["startedTime"]
    check(f"cluster {run} apps: queues root.parent.<u>, RUNNING, created u1<u2<u3",
          order and all(by[u]["queue"] == f"root.parent.{u}" and by[u]["state"] == "RUNNING" for u in by),
          f"u3 allocatedMB={by['u3']['allocatedMB']} running={by['u3'].get('runningContainers')}")
    sch = json.dumps(json.load(open(f"{L}/cluster/scheduler-{run}-end.json")))
    check(f"cluster {run} scheduler-end.json has root.parent.u3", '"queuePath": "root.parent.u3"' in sch)

for run in ("C1", "C2", "C3"):
    u3 = R[run]["u3"]
    check(f"cluster {run} u3 ~7168 MB, 6 hogs, RSS 3650+-10%",
          abs(u3["used"] - 7168) <= 1024 and u3["cnt"] == 6 and abs(u3["rss"] - 3650) <= 365,
          f"used={u3['used']} hog={u3['cnt']} rss={u3['rss']:.1f}")
check("cluster C1,C3 vs C2 within 1024 MB and 10% RSS",
      all(abs(R[c]["u3"]["used"] - R["C2"]["u3"]["used"]) <= 1024 and
          abs(R[c]["u3"]["rss"] - R["C2"]["u3"]["rss"]) <= 0.1 * R["C2"]["u3"]["rss"] for c in ("C1", "C3")))
c4 = R["C4"]["u3"]
check("cluster C4 control u3 <= 3072 MB, <=2 hogs, and C1-C4 >= 4096 MB",
      c4["used"] <= 3072 and c4["cnt"] <= 2 and R["C1"]["u3"]["used"] - c4["used"] >= 4096,
      f"used={c4['used']} hog={c4['cnt']} rss={c4['rss']:.1f}")
errs = {}
for f in sorted(glob.glob(f"{L}/cluster/client-*.log")):
    t = open(f, errors="replace").read()
    errs[os.path.basename(f)] = len(re.findall(r"\bERROR\b|Exception", t))
print(f"      client logs ERROR/Exception counts: {errs}")
print(f"== {len(fails)} FAIL: {fails}")
