#!/usr/bin/env python3
"""Self-check for CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous: re-parses the raw outputs and
compares them with the frozen predictions (B2f + A2/A3, B3f + A6-A8).

usage: selfcheck.py <surefire -output.txt> [<cluster-run.log>]
Prints PASS/FAIL per check and a summary.
"""
import re, sys

B = 4096; U = 1048576
res = []


def chk(name, ok, got):
    res.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ": " + str(got))


def kv(line):
    d = {}
    for f in line.strip().split(",")[1:]:
        if "=" in f:
            k, v = f.split("=", 1); d[k] = v
    return d


def fset(prefix, names):
    return ";".join(sorted(prefix + n for n in names)) if names else "-"


F = ["f01", "f02", "f03", "f04", "f05", "f06"]
UNIT = {  # (test, phase): (L, bytesNeeded, bytesCached, dnUsed, dnBlocks, overlimit, skipped)
    ("L0", "steady"): (0, 24576, 0, 0, 0, 24576, F),
    ("L2B", "steady"): (8192, 24576, 8192, 8192, 2, 16384, F[2:]),
    ("L2.5B", "steady"): (10240, 24576, 8192, 8192, 2, 14336, F[2:]),
    ("L4B", "steady"): (16384, 24576, 16384, 16384, 4, 8192, F[4:]),
    ("L6B", "steady"): (24576, 24576, 24576, 24576, 6, 0, []),
    ("unlimited", "steady"): (None, 24576, 24576, 24576, 6, 0, []),
    ("lowering", "steady"): (None, 24576, 24576, 24576, 6, 0, []),
    ("lowering", "after"): (12288, 24576, 12288, 12288, 3, 12288, F[3:]),
    ("order", "steady"): (12288, 20480, 4096, 4096, 1, 8192, ["a2", "a3"]),
    ("force", "steady"): (8192, 24576, 8192, 8192, 2, 16384, F[2:]),
    ("dncap", "steady"): (None, 24576, 12288, 12288, 3, 0, []),
}

txt = open(sys.argv[1]).read().splitlines()
rows = {}
for l in txt:
    if l.startswith("IFCHK,row,"):
        f = l.split(","); rows[(f[2], f[3])] = kv(",".join(f[3:]))
    elif l.startswith("IFCHK,addtime,noForce="):
        d = kv(l)
        chk("unit add-time without FORCE rejected with 'remaining capacity'",
            "InvalidRequestException" in d["noForce"] and "remaining capacity" in d["noForce"], d["noForce"][:140])
        # the RemoteException message carries the server stack on following lines; the field ends that block
        m = re.search(r"^,directivesAfterNoForce=(\d+)", "\n".join(txt), re.M) or re.search(r"directivesAfterNoForce=(\d+)", "\n".join(txt))
        chk("unit add-time: no directive created", m is not None and m.group(1) == "0", m and m.group(1))
    elif l.startswith("IFCHK,addtime,force="):
        chk("unit add-time with FORCE accepted", "accepted" in l, l)
    elif l.startswith("IFCHK,instr"):
        print("INFO " + l)
for key, (L, bn, bc, du, nb, ol, sk) in UNIT.items():
    r = rows.get(key)
    tag = "unit %s/%s" % key
    if r is None:
        chk(tag + " present", False, None); continue
    chk(tag + " settled", r["settled"] == "true", r["settled"] + " " + r["elapsedMs"] + " ms")
    got = (int(r["bytesNeeded"]), int(r["bytesCached"]), int(r["dnCacheUsed"]), int(r["dnBlocks"]),
           int(r["bytesOverlimit"]))
    chk(tag + " (BN,BC,DNused,DNblocks,OVER) = B2f", got == (bn, bc, du, nb, ol), "%s vs %s" % (got, (bn, bc, du, nb, ol)))
    chk(tag + " NN cached blocks = DN blocks", int(r["nnCached"]) == nb, r["nnCached"])
    pre = "/e/" if key[0] == "order" else "/d/"
    chk(tag + " skipped files (steady window) = A2", r["skipWindow"] == fset(pre, sk), r["skipWindow"])
    if L is not None:
        chk(tag + " BYTES_CACHED <= L and DN used <= L", got[1] <= L and got[2] <= L, (got[1], got[2], L))

if len(sys.argv) > 2:
    CL = {  # phase: (L, CacheUsed=BYTES_CACHED, blocks, VmLck delta kB, skipped)
        "unlimited": (None, 6 * U, 6, 6144, []),
        "L0": (0, 0, 0, 0, F),
        "L2U": (2 * U, 2 * U, 2, 2048, F[2:]),
        "L2.5U": (2621440, 2 * U, 2, 2048, F[2:]),
        "L4U": (4 * U, 4 * U, 4, 4096, F[4:]),
        "lowering-before": (None, 6 * U, 6, 6144, []),
        "lowering-after": (3 * U, 3 * U, 3, 3072, F[3:]),
        "force": (2 * U, 2 * U, 2, 2048, F[2:]),
        "dncap": (None, 3 * U, 3, 3072, []),
    }
    lines = open(sys.argv[2]).read().splitlines()
    cr = {}
    for l in lines:
        if l.startswith("CLCHK,"):
            cr[l.split(",")[1]] = kv(l)
    c = int(cr["L0"]["VmLckDelta_kB"]) if "L0" in cr else 0
    print("INFO VmLck constant offset c (L0 row) = %d kB" % c)
    for ph, (L, cu, nb, vm, sk) in CL.items():
        r = cr.get(ph); tag = "cluster " + ph
        if r is None:
            chk(tag + " present", False, None); continue
        chk(tag + " settled", r["settled"] == "True", r["settled"] + " t=" + r["t"])
        chk(tag + " BYTES_NEEDED = 6U", int(r["BYTES_NEEDED"]) == 6 * U, r["BYTES_NEEDED"])
        chk(tag + " CacheUsed = B3f", int(r["CacheUsed"]) == cu, r["CacheUsed"])
        chk(tag + " BYTES_CACHED = B3f", int(r["BYTES_CACHED"]) == cu, r["BYTES_CACHED"])
        chk(tag + " NumBlocksCached = B3f", int(r["NumBlocksCached"]) == nb, r["NumBlocksCached"])
        chk(tag + " VmLck delta - c = B3f (kB)", int(r["VmLckDelta_kB"]) - c == vm, "%s - %d vs %d" % (r["VmLckDelta_kB"], c, vm))
        chk(tag + " skipped files (window) = A8", r["skipWindow"] == fset("/d/", sk), r["skipWindow"])
        if L is not None:
            chk(tag + " CacheUsed <= L and VmLck delta - c <= L/1024 + 24", int(r["CacheUsed"]) <= L and
                int(r["VmLckDelta_kB"]) - c <= L // 1024 + 24, (r["CacheUsed"], r["VmLckDelta_kB"], L))
    t = "\n".join(lines)
    chk("cluster add-time without -force rejected ('remaining capacity')", "remaining capacity" in t, "")
    chk("cluster checknative hadoop: true", re.search(r"^hadoop:\s+true", t, re.M) is not None, "")
print("SUMMARY: %d PASS, %d FAIL" % (res.count(True), res.count(False)))
