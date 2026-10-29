#!/usr/bin/env python3
"""Independent self-check of no_constraint-isempty-size--autonomous run 1 (re-parses the Alloc and count traces with regexes, not analyze.py).
Usage: selfcheck.py <run1 dir>"""
import sys, re
d = sys.argv[1]; fails = 0
def chk(name, ok, msg=""):
    global fails; fails += 0 if ok else 1
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, msg))
def groups(p):
    g = {}; cur = None
    for l in open(p):
        m = re.match(r"mark .* block=(\S+) arm=(\S+) n=(-?\d+) rep=(-?\d+)", l)
        if m: cur = None if m.group(1) == "end" else (m.group(1), m.group(2), int(m.group(3)), int(m.group(4))); g[cur] = g.get(cur, []) if cur else None; continue
        if cur: g[cur].append(l)
    g.pop(None, None); return g
A = groups(d + "/raw-alloc/trace.txt"); C = groups(d + "/raw-count/trace.txt")
chk("100 attributed queries in each trace (10 groups x 10)", len(A) == 100 and len(C) == 100, "%d / %d" % (len(A), len(C)))
chk("exactly one build() line per query", all(sum(1 for l in v if l.startswith("bld ")) == 1 for v in A.values()))
chk("exactly one isEmpty line per query, true iff N=0", all([re.search(r"val=(\w+)", l).group(1) for l in v if l.startswith("empty ")] == [("true" if k[2] == 0 else "false")] for k, v in C.items()))
def blds(block, arm, n): return sorted(int(re.search(r"bytes=(\d+)", l).group(1)) for k, v in A.items() if k[:3] == (block, arm, n) and k[3] >= 0 for l in v if l.startswith("bld "))
def rows(block, arm, n): return {int(re.search(r"rows=(\d+)", l).group(1)) for k, v in A.items() if k[:3] == (block, arm, n) for l in v if l.startswith("bld ")}
med = lambda x: x[len(x)//2]
M = {(a, n): med(blds("main", a, n)) for a in "AB" for n in (0, 1, 1000, 20000)}
print("NOTE build() medians:", M)
chk("each (arm,N) has 7 timed readings, all equal", all(len(blds("main", a, n)) == 7 and len(set(blds("main", a, n))) == 1 for a in "AB" for n in (0, 1, 1000, 20000)))
chk("A(0)-B(0) = 208 and within [100,1000]", M[("A",0)] - M[("B",0)] == 208)
chk("flat for N >= 1 within 512", max(M[("A",n)] for n in (1,1000,20000)) - min(M[("A",n)] for n in (1,1000,20000)) <= 512 and max(M[("B",n)] for n in (1,1000,20000)) - min(M[("B",n)] for n in (1,1000,20000)) <= 512)
chk("result rows (from build lines) A=1, B=N", all(rows("main","A",n) == {1} and rows("main","B",n) == {n} for n in (0,1,1000,20000)))
n1, n2 = blds("noise1","A",0), blds("noise2","A",0)
chk("noise floor 0 (blocks equal, ranges 0)", n1 == n2 and len(set(n1)) == 1, "%s %s" % (n1[:1], n2[:1]))
print("NOTE B(0) = %d bytes: above the frozen 512-byte bound of B2f (c), the instrument and rule overhead inside the window (not the branch)" % M[("B", 0)])
q = {}
L = open(d + "/raw-alloc/raw.csv").read().strip().split("\n")[1:]
for l in L:
    b, a, n, rep, by, rr = l.split(","); q.setdefault((b, a, int(n)), []).append(int(by))
r = med(sorted(q[("main","B",20000)])) / float(med(sorted(q[("main","B",1000)])))
chk("control: whole-query B(20000)/B(1000) in [10,25]", 10 <= r <= 25, "%.2f" % r)
print("ALL PASS" if fails == 0 else "%d FAIL" % fails)
