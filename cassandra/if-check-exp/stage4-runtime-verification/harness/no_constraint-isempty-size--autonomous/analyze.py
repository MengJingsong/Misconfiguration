#!/usr/bin/env python3
"""Judge no_constraint-isempty-size--autonomous against the frozen predictions (case file B2f (a)-(e), amended 2026-10-29).
Usage: analyze.py <alloc-mode raw.csv> <alloc-mode trace.txt> <count-mode trace.txt>
Trace lines: "mark thread=.. ms=.. block=.. arm=.. n=.. rep=..", "bld thread=.. bytes=.. ms=.. rows=..", "empty thread=.. ms=.. val=.."."""
import csv, sys, statistics, collections
raw = list(csv.DictReader(open(sys.argv[1])))
def parse(p):
    """attribute bld / empty lines to the preceding mark; warm-up repeats (rep < 0) are kept apart."""
    cur = None; out = collections.defaultdict(list)
    for l in open(p):
        f = l.split()
        kv = {x.split("=",1)[0]: x.split("=",1)[1] for x in f[1:] if "=" in x}
        if f[0] == "mark": cur = (kv["block"], kv["arm"], int(kv["n"]), int(kv["rep"])) if kv["block"] != "end" else None
        elif f[0] in ("bld", "empty") and cur: out[cur].append((f[0], kv))
    return out
A = parse(sys.argv[2]); C = parse(sys.argv[3])
def line(name, ok, msg): print("PRED %-34s %s  %s" % (name, "PASS" if ok else "FAIL", msg))
def blds(block, arm, n):
    v = []
    for rep in range(0, 7):
        b = [int(kv["bytes"]) for t, kv in A[(block, arm, n, rep)] if t == "bld"]
        v.append(sum(b))
    return v
def med(v): return statistics.median(v)
nbl = collections.Counter(len([1 for t, kv in v if t == "bld"]) for v in A.values())
print("build() lines per query (all marks incl. warm-up): %s" % dict(nbl))
# (a) isEmpty per query
bad = []
for key, v in C.items():
    e = [kv["val"] for t, kv in v if t == "empty"]
    if len(e) != 1 or e[0] != ("true" if key[2] == 0 else "false"): bad.append((key, e))
line("(a) isEmpty once, true iff N=0", not bad and len(C) > 0, "%d queries checked, violations %s" % (len(C), bad[:4]))
# (b) result rows
rows = collections.defaultdict(set)
for r in raw: rows[(r["arm"], int(r["n"]))].add(int(r["result_rows"]))
okb = all(rows[("A", n)] == {1} and rows[("B", n)] == {n} for n in (0, 1, 1000, 20000))
line("(b) result rows A=1, B=N", okb, "A %s B %s" % ({n: sorted(rows[("A", n)]) for n in (0,1,1000,20000)}, {n: sorted(rows[("B", n)]) for n in (0,1,1000,20000)}))
# noise
n1, n2 = blds("noise1", "A", 0), blds("noise2", "A", 0)
floor = max(max(n1) - min(n1), max(n2) - min(n2), abs(med(n1) - med(n2)))
line("(e) noise floor <= 512 B", floor <= 512, "blocks medians %d / %d ranges %d / %d floor %d" % (med(n1), med(n2), max(n1)-min(n1), max(n2)-min(n2), floor))
M = {(a, n): med(blds("main", a, n)) for a in "AB" for n in (0, 1, 1000, 20000)}
R = {(a, n): max(blds("main", a, n)) - min(blds("main", a, n)) for a in "AB" for n in (0, 1, 1000, 20000)}
for k in sorted(M): print("  build() median arm %s N=%-6d %6d bytes (range %d)" % (k[0], k[1], M[k], R[k]))
line("(c) B(0) <= 512", M[("B", 0)] <= 512, "B(0)=%d" % M[("B", 0)])
d = M[("A", 0)] - M[("B", 0)]
line("(c) A(0)-B(0) in [100,1000]", 100 <= d <= 1000, "diff %d" % d)
tol = max(2 * floor, 512)
for a in "AB":
    v = [M[(a, n)] for n in (1, 1000, 20000)]
    line("(c) arm %s flat for N>=1" % a, max(v) - min(v) <= tol, "medians %s tolerance %d" % (v, tol))
line("(c) |A(0)-A(1)| small", abs(M[("A", 0)] - M[("A", 1)]) <= tol, "A(0)=%d A(1)=%d tolerance %d" % (M[("A", 0)], M[("A", 1)], tol))
# (d) control: whole query
q = collections.defaultdict(list)
for r in raw:
    if r["block"] == "main": q[(r["arm"], int(r["n"]))].append(int(r["query_bytes"]))
for k in sorted(q): print("  query bytes arm %s N=%-6d median %d" % (k[0], k[1], med(q[k])))
ratio = med(q[("B", 20000)]) / float(med(q[("B", 1000)]))
line("(d) control B(20000)/B(1000)", 10 <= ratio <= 25, "ratio %.2f" % ratio)
