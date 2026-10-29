#!/usr/bin/env python3
"""Independent self-check of no_constraint-hascomponent-i_nextsize--autonomous run 1 (re-parses raw.csv and trace.txt with plain split();
does not import analyze.py). Usage: selfcheck.py <run1 dir>"""
import sys, os
d = sys.argv[1]; fails = 0
def chk(name, ok, msg=""):
    global fails; fails += 0 if ok else 1
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, msg))
L = open(d + "/raw-plain/raw.csv").read().strip().split("\n"); h = L[0].split(","); R = [dict(zip(h, l.split(","))) for l in L[1:]]
chk("98 rows (14 points x 7)", len(R) == 98, "rows %d" % len(R))
def pts(block, label=None): return [r for r in R if r["block"] == block and (label is None or r["label"] == label)]
def med(xs): xs = sorted(xs); return xs[len(xs)//2]
main = pts("main")
exp = {(1,1):1,(2,1):1,(2,2):2,(2,4):2,(4,2):2,(4,4):4,(4,8):4,(8,8):8,(8,16):8,(16,16):16}
for (ns, s), k in exp.items():
    rs = [r for r in main if int(r["nextSize"]) == ns and int(r["S"]) == s]
    b = [int(r["bytes"]) for r in rs]
    chk("(%d,%d) %d x 1040 +-max(10%%,256)" % (ns, s, k), len(rs) == 7 and abs(med(b) - k * 1040) <= max(0.1 * k * 1040, 256) and all(int(r["deserializedSize"]) == k for r in rs) and all(r["thrown"] == "-" for r in rs), "median %d" % med(b))
noise = [int(r["bytes"]) for r in pts("noise1")] + [int(r["bytes"]) for r in pts("noise2")]
chk("noise: all (4,4) readings 4160 (range %d)" % (max(noise) - min(noise)), max(noise) - min(noise) < 256)
a = pts("control", "A-64k"); chk("control A 262208", med([int(r["bytes"]) for r in a]) == 262208, str(med([int(r["bytes"]) for r in a])))
b = pts("control", "B-maxvalue512")
print("NOTE control B: thrown %s, max_value_size column %s (setMaxValueSize(512) stores MiB, effective limit 0), median bytes %d" % (sorted({r["thrown"] for r in b}), sorted({r["maxValueSize"] for r in b}), med([int(r["bytes"]) for r in b])))
chk("control B threw", all(r["thrown"] != "-" for r in b))
tr = [l.split() for l in open(d + "/raw-bm/trace.txt") if l.strip()]
F = [t for t in tr if t[0] == "F"]; D = [t for t in tr if t[0] == "D"]
chk("F lines: 30 (10 calls each for nextSize 2, 4, 8), each with i == nextSize", len(F) == 30 and all(t[1] == t[2] for t in F) and sorted({t[2] for t in F}) == ["2", "4", "8"], "F %d" % len(F))
chk("D lines: 610 = 10 x (48 + 4 + 4) + 40 + 10 (expected from the point list)", len(D) == 610, "D %d" % len(D))
chk("junit logs OK", all("\nOK (1 test)" in open(d + "/junit-%s.log" % m).read() for m in ("plain", "bm")))
print("ALL PASS" if fails == 0 else "%d FAIL" % fails)
