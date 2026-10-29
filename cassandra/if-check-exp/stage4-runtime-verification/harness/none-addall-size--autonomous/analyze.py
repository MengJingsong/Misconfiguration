#!/usr/bin/env python3
"""Judge raw.csv (plain run) and trace.txt (Byteman run) of none-addall-size--autonomous against the frozen predictions
(case file B2f (i)-(vii) as amended 2026-10-29). Usage: analyze.py <plain raw.csv> <bm trace.txt> [<bm raw.csv>]
Prints one PRED line per prediction with PASS/FAIL and the numbers; does not decide the verdict (results file 8 does)."""
import csv, sys, statistics, collections, math

def load(p):
    rows = list(csv.DictReader(open(p)))
    for r in rows:
        for k in ("n","m","cap0","rep","bytes","size","cap","unshared","deep","bsz","eq"):
            r[k] = int(r[k])
        r["gf"] = float(r["gf"])
    return rows

rows = load(sys.argv[1])
trace = [l.split() for l in open(sys.argv[2])] if len(sys.argv) > 2 else []
G = collections.defaultdict(list)
for r in rows:
    G[(r["block"], r["sweep"], r["arm"], r["kind"], r["n"], r["m"])].append(r)

def med(key, f="bytes"): return statistics.median(x[f] for x in G[key])
def rng(key): v=[x["bytes"] for x in G[key]]; return max(v)-min(v)
def last(key, f): return G[key][-1][f]
def line(name, ok, msg): print("PRED %-34s %s  %s" % (name, "PASS" if ok else "FAIL", msg))

def cap_growth(cap0, need, gf=1.5):
    tot, c = 0, cap0
    while c < need:
        c = int(math.ceil(c * gf)); tot += 20 * c + 64
    return tot, c

# noise floor per arm
noise = {}
for arm in "PG":
    k1 = ("noise1","N",arm,"one",10000,1000); k2 = ("noise2","N",arm,"one",10000,1000)
    noise[arm] = max(rng(k1), rng(k2), abs(med(k1) - med(k2)))
    print("NOISE arm %s: block medians %d / %d, ranges %d / %d -> floor %d bytes" % (arm, med(k1), med(k2), rng(k1), rng(k2), noise[arm]))
print("EMPTY/baseline: see STAGE4 check lines in junit log")

main = [k for k in G if k[0] == "main" and k[3] == "one" and k[1] in ("S1","S2")]
# (i) arm P at most 4096
bad = [(k, med(k)) for k in main if k[2] == "P" and med(k) > 4096]
line("(i) arm P <= 4096 B", not bad, "max P median %d" % max(med(k) for k in main if k[2]=="P") + ("" if not bad else " violators %s" % bad))
# (ii) arm G closed form, within 10 percent
viol = []
for k in sorted(main):
    if k[2] != "G": continue
    exp, c = cap_growth(k[4], k[4] + k[5])
    got = med(k)
    ok = abs(got - exp) <= 0.10 * exp and last(k, "cap") == c
    print("  G %s n=%d m=%d: median %d expected %d (%+.2f%%) cap %d expected %d" % (k[1], k[4], k[5], got, exp, 100.0*(got-exp)/exp, last(k,"cap"), c))
    if not ok: viol.append(k)
line("(ii) arm G closed form +-10%", not viol, "violators %s" % viol)
# (iii) branch-adjacent pairs
def pair(a, b, arm, label):
    ka = [k for k in main if k[1]==a[0] and k[2]==arm and k[4]==a[1] and k[5]==a[2]][0]
    kb = [k for k in main if k[1]==b[0] and k[2]==arm and k[4]==b[1] and k[5]==b[2]][0]
    ea = cap_growth(ka[4], ka[4]+ka[5])[0] if arm=="G" else 0
    eb = cap_growth(kb[4], kb[4]+kb[5])[0] if arm=="G" else 0
    d = (med(kb) - eb) - (med(ka) - ea)
    tol = max(2 * noise[arm], 1024)
    line("(iii) %s arm %s" % (label, arm), abs(d) <= tol, "median %d vs %d, growth-adjusted diff %d, tolerance %d" % (med(ka), med(kb), d, tol))
for arm in "PG":
    pair(("S1",10000,999), ("S1",10000,1000), arm, "S1 m=999|1000")
    pair(("S2",10000,1000), ("S2",10001,1000), arm, "S2 n=10000|10001")
    ta = ("main","T",arm,"one",10000,1000); tb = ("main","T",arm,"twinadd",10000,1000)
    ma, mb = med(ta), med(tb)
    if arm == "P":
        ok = ma <= 4096 and mb <= 4096 + 256000
    else:
        ok = abs(ma - 300064) <= 30006 and abs(mb - 300064) <= 30006 + 256000
    line("(iii) twin T arm %s" % arm, ok, "T-merge %d, T-add %d (bytes per whole operation)" % (ma, mb))
# (iv) sizes, equals, branch counts
sizes_ok = all(x["size"] == x["n"] + x["m"] for x in rows)
eq_ok = all(x["eq"] == 1 for x in rows if x["eq"] != -1)
line("(iv) size == n+m, equals(ref)", sizes_ok and eq_ok, "all rows size ok=%s, equals ok=%s" % (sizes_ok, eq_ok))
if trace:
    cnt = collections.Counter((t[0], int(t[1]), int(t[2]), int(t[3])) for t in trace)
    # expectation per call: each (n,m,cap0) call executed WARM+REPS = 10 times; twinadd: m calls of (n+j, 1, cap) each 10 times
    bad = []
    seen_add = seen_mrg = 0
    for (b, n, m, cap), c in cnt.items():
        exp_b = "ADD" if n > 10 * m else "MRG"
        if b != exp_b: bad.append((b, n, m, cap, c))
        if b == "ADD": seen_add += c
        else: seen_mrg += c
    line("(iv) branch == (n > 10*m) in Byteman", not bad and seen_add > 0 and seen_mrg > 0, "ADD calls %d, MRG calls %d, contradictions %s" % (seen_add, seen_mrg, bad[:5]))
    # specific points seen with the right branch (m=500/999 add, 1000.. merge; n=10001,10010 add)
    for (n, m, want) in [(10000,500,"ADD"),(10000,999,"ADD"),(10000,1000,"MRG"),(10001,1000,"ADD"),(10010,1000,"ADD"),(9999,1000,"MRG")]:
        got = {b for (b, nn, mm, cap) in cnt if nn == n and mm == m}
        line("   branch n=%d m=%d" % (n, m), got == {want}, "seen %s" % sorted(got))
# (v) real retained size per element
per = {}
for k in G:
    if k[0] in ("main","control") and k[3]=="one" or (k[0]=="main" and k[3]=="twinadd"):
        if k[0] == "control": continue
        r = G[k][-1]; per[k] = (r["deep"] - (20 * r["cap"] + 64)) / float(r["size"])
vals = list(per.values()); spread = (max(vals) - min(vals)) / statistics.mean(vals)
line("(v) deep per element equal +-1%", spread <= 0.01, "per-element bytes min %.2f max %.2f spread %.3f%%" % (min(vals), max(vals), 100*spread))
for arm in "PG":
    da = last(("main","T",arm,"one",10000,1000), "deep"); db = last(("main","T",arm,"twinadd",10000,1000), "deep")
    line("(v) twin deep equal arm %s" % arm, abs(da - db) <= 64, "T-merge %d, T-add %d, diff %d" % (da, db, da - db))
# (vi) counter
for arm in "PG":
    ua = last(("main","T",arm,"one",10000,1000), "unshared"); ub = last(("main","T",arm,"twinadd",10000,1000), "unshared")
    bsz = last(("main","T",arm,"one",10000,1000), "bsz")
    line("(vi) counter T-add - T-merge arm %s" % arm, ub - ua == 1000 * bsz, "diff %d, 1000 x bsz = %d (bsz %d), capacities %d / %d" % (ub - ua, 1000 * bsz, bsz,
         last(("main","T",arm,"one",10000,1000),"cap"), last(("main","T",arm,"twinadd",10000,1000),"cap")))
# S1/S2 counters for the record
for k in sorted(main):
    if k[2] == "P": print("  COUNTER P %s n=%d m=%d unshared %d deep %d" % (k[1], k[4], k[5], last(k,"unshared"), last(k,"deep")))
# (vii) control
c = ("control","C","G","one",10000,1000); base = ("main","S1","G","one",10000,1000)
exp = 20 * 30000 + 64
line("(vii) control gf=3.0", abs(med(c) - exp) <= 0.10 * exp and med(c) >= 1.8 * med(base), "control median %d (expected %d), base %d, ratio %.2f, cap %d" % (med(c), exp, med(base), med(c)/float(med(base)), last(c,"cap")))
du = last(c, "unshared") - last(base, "unshared")
line("(vii) unshared rise", abs(du - 300000) <= 3000, "rise %d (expected 300000 +-1%%)" % du)
