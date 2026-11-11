#!/usr/bin/env python3
"""Results §5 self-check for MAX_KEY_SIZE-write-limit--autonomous (run with python3 -I).

Re-parses the raw surefire output file (not the run script's ifchk.csv) and the surefire reports, and prints
PASS/FAIL against the frozen B2f/A4/A5 thresholds and the B2g/A6 "grows" test.
Usage: selfcheck.py <run-dir>
"""
import glob
import os
import re
import sys

run = sys.argv[1]
out = os.path.join(run, "logs", "unit")
fails = 0


def check(name, ok, detail):
    global fails
    print(("PASS " if ok else "FAIL ") + name + ": " + detail)
    if not ok:
        fails += 1


raw = glob.glob(os.path.join(out, "*TestBoundedLimitHeap-output.txt"))
check("raw output file present", len(raw) == 1, str(raw))
lines = [l.rstrip("\n") for l in open(raw[0], encoding="utf-8", errors="replace") if l.startswith("IFCHK,")]

# surefire counts, from the XML-free text reports
for rep, want in (("TestBoundedLimitHeap.txt", 3),):
    p = glob.glob(os.path.join(out, "*" + rep))
    txt = open(p[0]).read() if p else ""
    m = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", txt)
    check("surefire " + rep, bool(m) and m.groups() == (str(want), "0", "0", "0"), m.group(0) if m else "missing")
for rep in ("TestBoundedByteArrayOutputStream.txt", "TestTFileStreams.txt"):
    p = glob.glob(os.path.join(out, "*" + rep))
    txt = open(p[0]).read() if p else ""
    m = re.search(r"Tests run: (\d+), Failures: (\d+), Errors: (\d+)", txt)
    check("surefire " + rep, bool(m) and m.group(2) == "0" and m.group(3) == "0", m.group(0) if m else "missing")

instr = [l for l in lines if l.startswith("IFCHK,instr,")]
check("instrument line", len(instr) == 1, instr[0] if instr else "missing")
kv = dict(x.split("=", 1) for x in instr[0].split(",")[2:] if "=" in x)
ka = int(kv["knownAnswer1MiB"])
check("instrument known answer 1 MiB array", 1048576 <= ka <= 1048576 + 256, str(ka))
check("instrument zero small", 0 <= int(kv["allocZero"]) <= 256, kv["allocZero"])
check("JVM options applied (heap <= 512 MiB, Serial GC 'Copy')",
      int(kv["maxHeap"]) <= 512 * 1024 * 1024 and kv["gc"] == "Copy", kv["maxHeap"] + " " + kv["gc"])

MiB = 1024 * 1024
direct = {}
for l in lines:
    f = l.split(",")
    if f[1] == "direct" and f[2].isdigit():
        (C, L, W, sizeAtFail, failIndex, allocCtor) = map(int, f[2:8])
        wpp, ipp = float(f[8]), float(f[9])
        exc_n = int(f[10]); exc = float(f[11]); res = float(f[12])
        zero, rdelta, rloop = int(f[13]), int(f[14]), int(f[15])
        same, blen, bad = f[16], int(f[17]), int(f[18])
        direct[(C, L)] = dict(wpp=wpp, ipp=ipp, res=res, exc=exc)
        tag = "C=%d L=%d" % (C, L)
        check(tag + " W=L+1024", W == L + 1024, str(W))
        check(tag + " failIndex=L+1, sizeAtFail=L, badPasses=0", failIndex == L + 1 and sizeAtFail == L and bad == 0,
              "%d %d %d" % (failIndex, sizeAtFail, bad))
        check(tag + " exceptions=102400", exc_n == 102400, str(exc_n))
        check(tag + " buffer same, length C", same == "true" and blen == C, "%s %d" % (same, blen))
        check(tag + " C <= allocCtor <= C+256", C <= allocCtor <= C + 256, str(allocCtor))
        check(tag + " allocInPerPass < 1024", ipp < 1024, "%.2f" % ipp)
        check(tag + " residualPerPass < 1024", res < 1024, "%.2f (writes/pass %.2f, excCost %.2f)" % (res, wpp, exc))
        check(tag + " retainedDelta in C +- 1 MiB", abs(rdelta - C) <= MiB, str(rdelta))
        check(tag + " |retainedLoop| <= 1 MiB", abs(rloop) <= MiB, str(rloop))
        if L >= 512 * 1024:
            check(tag + " allocInPerPass < 1% of L (refuted-if)", ipp < 0.01 * L, "%.2f vs %.0f" % (ipp, 0.01 * L))
check("9 direct rows", len(direct) == 9, str(len(direct)))
big = 16777216
lo, hi = direct[(big, 1024)], direct[(big, big)]
thr = 0.01 * (big - 1024)
check("grows test (allocIn, C=16MiB, L=16MiB vs 1024) not met", hi["ipp"] - lo["ipp"] <= thr,
      "%.2f - %.2f vs %.0f" % (hi["ipp"], lo["ipp"], thr))
check("grows test (residual, C=16MiB, L=16MiB vs 1024) not met", hi["res"] - lo["res"] <= thr,
      "%.2f - %.2f vs %.0f" % (hi["res"], lo["res"], thr))

want = {"writeByte": (65537, 65536), "writeByteDecl100": (101, 100), "writeInt": (16385, 65536)}
tf = [l.split(",") for l in lines if l.startswith("IFCHK,tfile,write")]
check("3 TFile rows", len(tf) == 3, str(len(tf)))
for f in tf:
    name = f[2]
    failAt, size, aw, al = int(f[5]), int(f[6]), int(f[7]), int(f[8])
    res = float(f[10])
    check("TFile %s fails at %d, size %d" % (name, *want[name]), (failAt, size) == want[name], "%d %d" % (failAt, size))
    check("TFile %s loop alloc - excCost < 1024" % name, res < 1024, "%d - %s = %.2f" % (al, f[9], res))
    check("TFile %s Writer alloc >= 131072" % name, aw >= 131072, str(aw))
    check("TFile %s key buffer length 65536" % name, int(f[11]) == 65536, f[11])

ctrl = [l.split(",") for l in lines if re.match(r"IFCHK,control,(ByteArrayOutputStream|DataOutputBuffer),", l)]
check("18 control rows", len(ctrl) == 18, str(len(ctrl)))
for s in ("ByteArrayOutputStream", "DataOutputBuffer"):
    rows = {int(f[5]): float(f[6]) for f in ctrl if f[2] == s}
    for w, a in sorted(rows.items()):
        check("control %s W=%d: W <= alloc <= 4W+1024" % (s, w), w <= a <= 4 * w + 1024, "%.0f (ratio %.3f)" % (a, a / w))
    wmin, wmax = min(rows), max(rows)
    check("control %s grows > 1000x (W %d -> %d)" % (s, wmin, wmax), rows[wmax] > 1000 * rows[wmin],
          "%.0f / %.0f = %.0f" % (rows[wmax], rows[wmin], rows[wmax] / rows[wmin]))

print("SUMMARY: %d FAIL" % fails)
