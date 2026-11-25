#!/usr/bin/env python3
# Checks the unit readings (readings.csv from unit-run.sh) against B2f of
# DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.
# ROW,<case>,i,M,D,AD,DC,HB   (M counter, D dump length, AD ALLOW_DUMP sum, DC DUMPED count,
#                              HB payload bytes still referenced by WriteCtx.data)
# Usage: python3 -I check-unit.py readings.csv
import sys

C = 65536
W = {"wm256k": 262144, "wm1m": 1048576, "wm4m": 4194304,
     "dumpDisabled": 1048576, "dumpDirMissing": 1048576}
rows, summ, blocked = {}, {}, {}
for line in open(sys.argv[1]):
    f = line.strip().split(",")
    if f[0] == "ROW":
        rows.setdefault(f[1], []).append([int(x) for x in f[2:]])
    elif f[0] == "SUMMARY":
        summ[f[1]] = dict(kv.split("=", 1) for kv in f[2:])
    elif f[0] == "BLOCKED":
        blocked[f[1]] = [int(x) for x in f[2:]]

for case in ["wm256k", "wm1m", "wm4m", "dumpDisabled", "dumpDirMissing"]:
    rs = rows.get(case, [])
    m = W[case] // C
    bad = 0
    steps = set()
    prev_d = 0
    max_m = 0
    for i, M, D, AD, DC, HB in rs:
        if case in ("wm256k", "wm1m", "wm4m"):
            exp = dict(M=(i % m) * C, D=(i - i % m) * C, AD=(i % m) * C,
                       DC=(i - i % m), HB=(i % m) * C)
        elif case == "dumpDisabled":
            exp = dict(M=i * C, D=-1, AD=i * C, DC=0, HB=i * C)
        else:  # dumpDirMissing: rows 1..15 return, no dump file (length 0)
            exp = dict(M=i * C, D=0, AD=i * C, DC=0, HB=i * C)
        got = dict(M=M, D=D, AD=AD, DC=DC, HB=HB)
        if got != exp:
            bad += 1
            if bad <= 3:
                print("  mismatch", case, i, got, exp)
        if case in ("wm256k", "wm1m", "wm4m") and M + D != i * C:
            bad += 1
            print("  M+D != i*C", case, i)
        if D > prev_d:
            steps.add(D - prev_d)
            prev_d = D
        max_m = max(max_m, M)
    s = summ.get(case, {})
    last = rs[-1] if rs else None
    print("%s: rows=%d mismatches=%d maxMAfterReturn=%d (W=%d, below W: %s) dump steps=%s "
          "last row=%s logPeak=%s createDumpLines=%s dumpRounds(obs)=%s "
          "dumpDecrementLines=%s blocked=%s failureLogged=%s" % (
              case, len(rs), bad, max_m, W[case], max_m < W[case], sorted(steps), last,
              s.get("logPeak"), s.get("createDumpLines"),
              s.get("dumpRoundsObserved"), s.get("dumpDecrements"), s.get("blocked"),
              s.get("dumpFailureLogged")))
    if case in blocked:
        print("  BLOCKED at write %d: M=%d D=%d AD=%d DC=%d HB=%d" % tuple(blocked[case]))
if "concurrent4" in summ:
    s = summ["concurrent4"]
    print("concurrent4:", s, "peak bound 1245184 respected:",
          int(s["logPeak"]) <= 1245184)
