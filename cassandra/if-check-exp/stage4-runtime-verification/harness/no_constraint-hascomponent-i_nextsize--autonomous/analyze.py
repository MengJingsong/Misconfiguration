#!/usr/bin/env python3
"""Judge raw.csv (plain run) and trace.txt (Byteman run) of no_constraint-hascomponent-i_nextsize--autonomous against the frozen
predictions (case file B2f as amended 2026-10-29). Usage: analyze.py <plain raw.csv> [<bm trace.txt>]"""
import csv, sys, statistics, collections
rows = list(csv.DictReader(open(sys.argv[1])))
for r in rows:
    for k in ("nextSize","S","compSize","rep","bytes","deserializedSize","cmp","streamLen","maxValueSize"): r[k] = int(r[k])
G = collections.defaultdict(list)
for r in rows: G[(r["block"], r["label"], r["nextSize"], r["S"], r["compSize"])].append(r)
def med(k): return statistics.median(x["bytes"] for x in G[k])
def rng(k): v = [x["bytes"] for x in G[k]]; return max(v) - min(v)
def line(name, ok, msg): print("PRED %-34s %s  %s" % (name, "PASS" if ok else "FAIL", msg))
k1 = ("noise1","N",4,4,1024); k2 = ("noise2","N",4,4,1024)
floor = max(rng(k1), rng(k2), abs(med(k1) - med(k2)))
print("NOISE (4,4): block medians %d / %d, ranges %d / %d -> floor %d bytes" % (med(k1), med(k2), rng(k1), rng(k2), floor))
line("noise floor < 256 B", floor < 256, "floor %d" % floor)
sweep = sorted(k for k in G if k[0] == "main")
bad = []
for k in sweep:
    ns, s = k[2], k[3]; exp = min(s, ns) * 1040; got = med(k); tol = max(0.10 * exp, 256)
    ds = {x["deserializedSize"] for x in G[k]}; thrown = {x["thrown"] for x in G[k]}
    ok = abs(got - exp) <= tol and ds == {min(s, ns)} and thrown == {"-"}
    print("  (%d,%d): median %d range %d expected %d (%+d) deserializedSize %s thrown %s" % (ns, s, got, rng(k), exp, got - exp, sorted(ds), sorted(thrown)))
    if not ok: bad.append((ns, s))
line("allocation = min(S,nextSize) x 1040", not bad, "violators %s" % bad)
for a, b in [((2,2),(2,4)), ((4,4),(4,8)), ((8,8),(8,16))]:
    ka = ("main","S",a[0],a[1],1024); kb = ("main","S",b[0],b[1],1024)
    d = med(kb) - med(ka); tol = max(2 * floor, 256)
    line("flip pair %s|%s" % (a, b), abs(d) <= tol, "medians %d vs %d, diff %d, tolerance %d" % (med(ka), med(kb), d, tol))
kc = ("control","A-64k",4,4,65536); exp = 4 * 65552
line("control A (64 KiB)", abs(med(kc) - exp) <= 0.1 * exp and med(kc) >= 50 * med(("main","S",4,4,1024)), "median %d expected %d ratio to 1 KiB reading %.1f" % (med(kc), exp, med(kc) / float(med(("main","S",4,4,1024)))))
kb_ = ("control","B-maxvalue512",4,4,1024)
th = {x["thrown"] for x in G[kb_]}
line("control B (max_value_size 512)", th != {"-"} and med(kb_) < 1040 + 4096, "thrown %s median bytes %d maxValueSize %s" % (sorted(th), med(kb_), sorted({x["maxValueSize"] for x in G[kb_]})))
if len(sys.argv) > 2:
    tr = [l.split() for l in open(sys.argv[2])]
    F = collections.Counter(int(t[2]) for t in tr if t[0] == "F"); D = sum(1 for t in tr if t[0] == "D")
    # expected F per call count: calls = 10 per point (3 warm-up + 7), every block incl. noise and controls where S > nextSize
    exp = collections.Counter()
    for k in G:
        if k[3] > k[2] and k[0] != "control":   # the control B point throws before; A has S == nextSize
            exp[k[2]] += 10
    # control B (S == nextSize, throws) adds none
    line("false returns per nextSize", F == exp, "observed %s expected %s; deserializeOne entries %d" % (dict(F), dict(exp), D))
