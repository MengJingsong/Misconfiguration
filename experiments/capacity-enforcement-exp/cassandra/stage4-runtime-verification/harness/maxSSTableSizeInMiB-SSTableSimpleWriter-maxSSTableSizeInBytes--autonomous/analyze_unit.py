#!/usr/bin/env python3
"""Analyze probe-unit.csv against B2f/B2g as amended by S2 and S3 (frozen 2026-11-24 before any reading).
Usage: analyze_unit.py probe-unit.csv [poscontrol-log]"""
import sys, math, csv
from collections import OrderedDict

MiB = 1048576
CMAX = 16472
rows = list(csv.reader(open(sys.argv[1])))
runs = OrderedDict()
seq = 0
prev_key = None
for r in rows:
    label, m, comp, limit, idx, data, allc, op = r
    idx = int(idx)
    if idx == 0:
        seq += 1
    key = (seq, label, int(m), comp == 'true', int(limit))
    runs.setdefault(key, []).append((idx, int(data), int(allc), int(op) if op else None))

ok = bad = 0
def check(cond, msg):
    global ok, bad
    if cond: ok += 1
    else: bad += 1
    print(("  ok   " if cond else "  BAD  ") + msg)
    return cond

counts = {}
print("run summary")
for (seq, label, m, comp, limit), sst in runs.items():
    T = sum(s[1] for s in sst)
    A = sum(s[2] for s in sst)
    nrows = 64999 if label == 'bigpart' else 60000
    P = T / nrows
    Pb = math.ceil(P) + 16
    n = len(sst)
    mm = 'unset' if m == -2147483648 else m
    print(f"#{seq} {label} M={mm} comp={comp} limitBytes={limit} sstables={n} T={T} allComp={A} P={P:.2f} Pb={Pb}")
    L = m * MiB if m > 0 else None
    nonlast = sst[:-1]
    if nonlast:
        d = [s[1] for s in nonlast]
        print(f"     non-last Data.db min={min(d)} max={max(d)}  (minus L: {min(d)-(L or 0)}..{max(d)-(L or 0)})" if L else f"     non-last Data.db min={min(d)} max={max(d)}")
        ops = [s[3] for s in nonlast]
        if all(o is not None for o in ops):
            diffs = [s[1] - s[3] for s in nonlast]
            print(f"     operandAtSwitch min={min(ops)} max={max(ops)}; Data-operand min={min(diffs)} max={max(diffs)}")
            ac = [s[2] - (L or 0) for s in nonlast]
            print(f"     allComponents - L: min={min(ac)} max={max(ac)}  (={100*min(ac)/(L or 1):.2f}%..{100*max(ac)/(L or 1):.2f}% of L)")
    print(f"     last Data.db={sst[-1][1]}")
    counts[(label, mm, comp)] = (n, T, L, Pb, sst, limit)

print("\nchecks (B2f/B2g with S2, S3)")
for comp in (False, True):
    for m in (1, 4, 16):
        n, T, L, Pb, sst, limit = counts[('sorted', m, comp)]
        tag = f"sorted M={m} comp={comp}"
        check(limit == m * MiB, f"{tag}: limitBytes {limit} == {m*MiB}")
        check(T >= 40_000_000, f"{tag}: T {T} >= 40 MB")
        exp = math.ceil(T / L)
        check(abs(n - exp) <= max(1, 0.1 * exp), f"{tag}: count {n} vs ceil(T/L) {exp}")
        nonlast = sst[:-1]
        if not comp:
            check(all(L < s[1] <= L + Pb for s in nonlast), f"{tag}: every non-last Data.db in (L, L+Pb] = ({L}, {L+Pb}]")
            check(all(s[3] == s[1] for s in nonlast), f"{tag}: operandAtSwitch == Data.db for every non-last")
            check(sst[-1][1] <= L + Pb, f"{tag}: last Data.db {sst[-1][1]} <= L+Pb")
        else:
            check(all(L < s[1] <= L + 2 * CMAX for s in nonlast), f"{tag}: every non-last Data.db in (L, L+2*Cmax] = ({L}, {L+2*CMAX}]")
            check(all(L < s[3] <= L + CMAX for s in nonlast), f"{tag}: operandAtSwitch in (L, L+Cmax]")
            check(all(0 <= s[1] - s[3] <= CMAX for s in nonlast), f"{tag}: 0 <= Data.db - operand <= Cmax")
            filed = [s for s in nonlast if s[1] > L + Pb + 16388]
            print(f"  info {tag}: non-last over the FILED bound L+P+16,388 (secondary, S2): {len(filed)} of {len(nonlast)}")
    c1, c4, c16 = (counts[('sorted', m, comp)][0] for m in (1, 4, 16))
    check(abs(c1 - 4 * c4) <= 2, f"comp={comp}: |c1 - 4*c4| = |{c1} - {4*c4}| <= 2")
    check(abs(c4 - 4 * c16) <= 2, f"comp={comp}: |c4 - 4*c16| = |{c4} - {4*c16}| <= 2")
    for m in (0, 'unset'):
        n, T, L, Pb, sst, limit = counts[('sorted', m, comp)]
        check(n == 1, f"sorted M={m} comp={comp}: exactly 1 SSTable (got {n}), Data.db={sst[0][1]}")
        check(limit == -MiB, f"sorted M={m} comp={comp}: limitBytes {limit} == -1048576")
        check(T >= 40_000_000, f"sorted M={m} comp={comp}: T {T} >= 40 MB")
n, T, L, Pb, sst, limit = counts[('bigpart', 1, False)]
check(sst[0][1] > 4.5 * MiB and sst[0][3] == sst[0][1], f"bigpart: first Data.db {sst[0][1]} > 4.5 MiB and operand {sst[0][3]} equal")
check(3 <= n <= 5, f"bigpart: {n} SSTables in 3..5")
check(all(L < s[1] <= L + Pb for s in sst[1:-1]), "bigpart: later non-last in (L, L+Pb]")
n, T, L, Pb, sst, limit = counts[('unsorted', 4, False)]
check(n >= 2, f"unsorted control M=4: {n} SSTables >= 2 (sizes {[s[1] for s in sst]})")
if len(sys.argv) > 2:
    log = open(sys.argv[2]).read()
    check('BUILD SUCCESSFUL' in log and 'Failures: 0, Errors: 0' in log, "positive control testWriteWithSortedAndMaxSize passed")
print(f"\nCHECKS ok={ok} bad={bad}")
