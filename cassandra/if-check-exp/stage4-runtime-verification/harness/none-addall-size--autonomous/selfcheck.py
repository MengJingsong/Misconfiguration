#!/usr/bin/env python3
"""Independent self-check of none-addall-size--autonomous run 1: re-parses raw.csv and trace.txt WITHOUT analyze.py (plain split(), own growth
arithmetic, own expected counts) and compares with analysis.txt. Usage: selfcheck.py <run1 dir>"""
import sys, os, math
d = sys.argv[1]; fails = 0
def chk(name, ok, msg=""):
    global fails; fails += 0 if ok else 1
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, msg))
lines = open(d + "/raw-plain/raw.csv").read().strip().split("\n")
hdr = lines[0].split(","); R = [dict(zip(hdr, l.split(","))) for l in lines[1:]]
chk("row count 203 (27 one-points + 2 twin... = 29 points x 7)", len(R) == 203 + 0 or len(R) == 29 * 7, "rows %d" % len(R))
def rows(**kw): return [r for r in R if all(r[k] == str(v) for k, v in kw.items())]
def med(xs): xs = sorted(xs); return xs[len(xs)//2]
# independent growth arithmetic
def growth(cap, need):
    t = 0
    while cap < need:
        cap = int(-(-cap * 3 // 2)) if True else cap   # ceil(cap * 1.5) with integers
        t += 4 * 16 + 20 * cap
    return t, cap
for (n, m) in [(10000, 500), (10000, 999), (10000, 1000), (10000, 1001), (10000, 2000), (10000, 10000), (9999, 1000), (10001, 1000), (10010, 1000)]:
    sw = "S1" if n == 10000 and (n, m) != (10000, 1000) else "S2" if m == 1000 and n != 10000 else "S1"
    rs = [r for r in R if r["block"] == "main" and r["kind"] == "one" and r["arm"] == "G" and int(r["n"]) == n and int(r["m"]) == m and r["sweep"] in ("S1", "S2")]
    exp, cap = growth(n, n + m)
    got = med([int(r["bytes"]) for r in rs])
    chk("G n=%d m=%d closed form" % (n, m), len(rs) >= 7 and abs(got - exp) <= 0.1 * exp and all(int(r["cap"]) == cap for r in rs), "got %d exp %d cap %d" % (got, exp, cap))
chk("arm P all calls <= 4096", all(int(r["bytes"]) <= 4096 for r in R if r["arm"] == "P" and r["block"] == "main" and r["kind"] == "one"))
chk("every size == n+m", all(int(r["size"]) == int(r["n"]) + int(r["m"]) for r in R))
chk("equals(reference) where tested", all(r["eq"] == "1" for r in R if r["eq"] != "-1") and sum(1 for r in R if r["eq"] == "1") >= 29)
for arm in "PG":
    a = rows(block="main", sweep="T", arm=arm, kind="one")[-1]; b = rows(block="main", sweep="T", arm=arm, kind="twinadd")[-1]
    chk("twin arm %s deep equal" % arm, abs(int(a["deep"]) - int(b["deep"])) <= 64, "%s vs %s" % (a["deep"], b["deep"]))
    chk("twin arm %s counter diff = 1000 x bsz" % arm, int(b["unshared"]) - int(a["unshared"]) == 1000 * int(a["bsz"]), "diff %d bsz %s" % (int(b["unshared"]) - int(a["unshared"]), a["bsz"]))
    chk("twin arm %s alloc comparable" % arm, abs(med([int(r["bytes"]) for r in rows(block="main", sweep="T", arm=arm, kind="one")]) - med([int(r["bytes"]) for r in rows(block="main", sweep="T", arm=arm, kind="twinadd")])) <= 1024)
# counter step at the flip (reported, not a verdict row)
u = lambda sw, n, m: int(rows(block="main", sweep=sw, arm="P", kind="one", n=n, m=m)[-1]["unshared"])
dd = lambda sw, n, m: int(rows(block="main", sweep=sw, arm="P", kind="one", n=n, m=m)[-1]["deep"])
print("NOTE counter vs deep at the flip (arm P): m=999 unshared %d deep %d | m=1000 unshared %d deep %d" % (u("S1",10000,999), dd("S1",10000,999), u("S1",10000,1000), dd("S1",10000,1000)))
chk("counter jumps at the flip while deep is continuous", u("S1",10000,999) - u("S1",10000,1000) > 200000 and abs(dd("S1",10000,999) - dd("S1",10000,1000)) < 1000)
# control
c = rows(block="control"); g = rows(block="main", sweep="S1", arm="G", kind="one", n=10000, m=1000)
chk("control gf=3.0 allocation 600064 and 2x", med([int(r["bytes"]) for r in c]) == 600064 and med([int(r["bytes"]) for r in c]) >= 1.8 * med([int(r["bytes"]) for r in g]), "control %d base %d gf %s" % (med([int(r["bytes"]) for r in c]), med([int(r["bytes"]) for r in g]), c[0]["gf"]))
# noise
nz = {}
for arm in "PG":
    b1 = [int(r["bytes"]) for r in rows(block="noise1", arm=arm)]; b2 = [int(r["bytes"]) for r in rows(block="noise2", arm=arm)]
    nz[arm] = max(max(b1) - min(b1), max(b2) - min(b2), abs(med(b1) - med(b2)))
print("NOTE noise floor P %d G %d" % (nz["P"], nz["G"]))
# trace: own counting
tr = [l.split() for l in open(d + "/raw-bm/trace.txt") if l.strip()]
add = [t for t in tr if t[0] == "ADD"]; mrg = [t for t in tr if t[0] == "MRG"]
chk("trace totals: 20270 calls = 20080 ADD + 190 MRG (expected from the point list)", len(add) == 20080 and len(mrg) == 190, "ADD %d MRG %d" % (len(add), len(mrg)))
chk("every ADD has n > 10m, every MRG has n <= 10m", all(int(t[1]) > 10 * int(t[2]) for t in add) and all(int(t[1]) <= 10 * int(t[2]) for t in mrg))
# environment evidence
chk("harness md5 file present", os.path.exists(d + "/harness.md5"))
chk("junit logs report OK", all("\nOK (1 test)" in open(d + "/junit-%s.log" % m).read() for m in ("plain", "bm")))
print("ALL PASS" if fails == 0 else "%d FAIL" % fails)
