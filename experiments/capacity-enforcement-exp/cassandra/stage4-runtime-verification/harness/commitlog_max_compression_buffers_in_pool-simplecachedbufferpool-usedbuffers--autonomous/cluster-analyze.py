#!/usr/bin/env python3
"""Cluster-tier analyzer: B3f predictions as EXPECTED lines, B3g row per audit amendment M8.
usage: cluster-analyze.py <run-dir>   (reads <run-dir>/<cfg>/{events.txt,samples.csv,jstack/*.txt} for N3 N6 N12 C1 C2)"""
import glob
import os
import statistics
import sys

R = sys.argv[1]
MIB = 1 << 20
S = 64 * MIB
n_pass = n_fail = 0


def expect(ok, text):
    global n_pass, n_fail
    print(f"EXPECTED {'PASS' if ok else 'FAIL'}: {text}")
    n_pass += ok
    n_fail += (not ok)


def load(cfg):
    d = f"{R}/{cfg}"
    if not os.path.exists(f"{d}/samples.csv"):
        return None
    ev = {}
    for ln in open(f"{d}/events.txt"):
        k, v = ln.split()
        ev.setdefault(k, int(v))
    rows = []
    for ln in open(f"{d}/samples.csv"):
        if ln.startswith(("epoch", "#")):
            continue
        f = [int(x) for x in ln.strip().split(",")]
        rows.append(dict(zip("t direct dcount mapped wosa woc bpnet bpchunk heap".split(), f)))
    s0, s1 = ev["stress_start"], ev["stress_end"]
    idle = [r for r in rows if s0 - 30000 <= r["t"] <= s0 and r["direct"] >= 0]
    win = [r for r in rows if s0 <= r["t"] <= s1 and r["direct"] >= 0]
    b0 = statistics.median(r["direct"] for r in idle)
    pk = max(win, key=lambda r: r["direct"])
    before = [r for r in rows if r["t"] <= s0 and r["wosa"] >= 0]
    upto = [r for r in rows if r["t"] <= s1 and r["wosa"] >= 0]
    wosa = upto[-1]["wosa"] - before[-1]["wosa"]
    woc = upto[-1]["woc"] - before[-1]["woc"]
    # jstack dumps inside the stress window
    dumps = []
    for f in sorted(glob.glob(f"{d}/jstack/*.txt")):
        t = int(os.path.basename(f)[:-4])
        if not (s0 <= t <= s1):
            continue
        txt = open(f, errors="replace").read()
        blocks = txt.split("\n\n")
        alloc = [b for b in blocks if b.startswith('"COMMIT-LOG-ALLOCATOR')]
        alloc_wait = bool(alloc) and "WaitQueue.waitOnCondition" in alloc[0] and "createSegment" not in alloc[0]
        writers = sum(1 for b in blocks if "AbstractCommitLogSegmentManager.awaitAvailableSegment" in b)
        dumps.append((t, alloc_wait, writers, bool(alloc)))
    blocked_dumps = [x for x in dumps if x[1] and x[2] >= 1]
    blocked = wosa >= 1 and len(blocked_dumps) >= 1
    # time from stress start until direct first reaches 95 % of its in-window peak (context)
    tp = next(r["t"] for r in win if r["direct"] >= b0 + 0.95 * (pk["direct"] - b0)) - s0 if pk["direct"] > b0 else 0
    ctx = dict(bpnet0=statistics.median(r["bpnet"] for r in idle), bpnet_max=max(r["bpnet"] for r in win),
               bpchunk0=statistics.median(r["bpchunk"] for r in idle), bpchunk_max=max(r["bpchunk"] for r in win),
               mapped0=statistics.median(r["mapped"] for r in idle), mapped_max=max(r["mapped"] for r in win),
               heap_max=max(r["heap"] for r in win), dcount0=statistics.median(r["dcount"] for r in idle),
               dcount_at_peak=pk["dcount"])
    return dict(cfg=cfg, b0=b0, P=pk["direct"], tpeak=pk["t"] - s0, t95=tp, nidle=len(idle), nwin=len(win),
                dur=(s1 - s0) / 1000, wosa=wosa, woc=woc, dumps=len(dumps), blocked_dumps=len(blocked_dumps),
                max_writers=max([x[2] for x in dumps] or [0]), alloc_seen=sum(x[3] for x in dumps), blocked=blocked, **ctx)


res = {c: load(c) for c in ("N3", "N6", "N12", "C1", "C2")}
for c, r in res.items():
    if r is None:
        print(f"# {c}: no data")
        continue
    print(f"# {c}: B0={r['b0'] / MIB:.1f} MiB P={r['P'] / MIB:.1f} MiB P-B0={(r['P'] - r['b0']) / MIB:.1f} MiB "
          f"(={(r['P'] - r['b0']) / S:.2f} S) peak at +{r['tpeak'] / 1000:.0f} s, 95% at +{r['t95'] / 1000:.0f} s; stress {r['dur']:.0f} s; "
          f"samples idle/window {r['nidle']}/{r['nwin']}; dWaitingOnSegmentAllocation={r['wosa']} dWaitingOnCommit={r['woc']}; "
          f"jstack in window {r['dumps']} (allocator seen {r['alloc_seen']}), blocked-state dumps {r['blocked_dumps']}, max writers in awaitAvailableSegment {r['max_writers']}; "
          f"direct count {r['dcount0']:.0f}->{r['dcount_at_peak']}; BufferPool networking {r['bpnet0'] / MIB:.1f}->{r['bpnet_max'] / MIB:.1f} MiB, "
          f"chunk-cache {r['bpchunk0'] / MIB:.1f}->{r['bpchunk_max'] / MIB:.1f} MiB; mapped {r['mapped0'] / MIB:.1f}->{r['mapped_max'] / MIB:.1f} MiB; heap max {r['heap_max'] / MIB:.0f} MiB")

Z = {3: res["N3"], 6: res["N6"], 12: res["N12"]}
if all(Z.values()):
    d = {n: Z[n]["P"] - Z[n]["b0"] for n in Z}
    ok_ceiling = all(d[n] <= (n - 1) * S + 64 * MIB for n in Z)
    ok_floor = all(d[n] >= (n - 3) * S for n in Z)
    for n in Z:
        expect(d[n] <= (n - 1) * S + 64 * MIB, f"B3f ceiling N={n}: P-B0 <= (N-2)S + S + 64 MiB = {((n - 1) * S + 64 * MIB) / MIB:.0f} MiB (got {d[n] / MIB:.1f})")
        expect(d[n] >= (n - 3) * S, f"B3f plateau N={n}: P-B0 >= (N-3)S = {(n - 3) * S / MIB:.0f} MiB (got {d[n] / MIB:.1f})")
        expect(Z[n]["blocked"], f"B3f writers blocked N={n}: dWOSA={Z[n]['wosa']} >= 1 and blocked-state jstack dumps={Z[n]['blocked_dumps']} >= 1")
    s1 = (Z[6]["P"] - Z[3]["P"]) / MIB
    s2 = (Z[12]["P"] - Z[6]["P"]) / MIB
    ok_s1, ok_s2 = abs(s1 - 192) <= 64, abs(s2 - 384) <= 64
    expect(ok_s1, f"B3f slope P(6)-P(3) = 192 +-64 MiB (got {s1:.1f}; B0-differenced {(d[6] - d[3]) / MIB:.1f})")
    expect(ok_s2, f"B3f slope P(12)-P(6) = 384 +-64 MiB (got {s2:.1f}; B0-differenced {(d[12] - d[6]) / MIB:.1f})")
    all_blocked = all(Z[n]["blocked"] for n in Z)
    none_blocked = not any(Z[n]["blocked"] for n in Z)
    row1 = ok_ceiling and ok_floor and ok_s1 and ok_s2 and all_blocked
    row2 = any(d[n] > (n - 1) * S + 64 * MIB for n in Z)
    Ps = [Z[n]["P"] for n in Z]
    row3 = (max(Ps) - min(Ps)) <= 64 * MIB and all_blocked
    row4 = none_blocked and all(d[n] < (n - 3) * S for n in Z)
else:
    row1 = row2 = row3 = row4 = False
    print("# missing Zstd runs")

c1, c2 = res["C1"], res["C2"]
row5 = row6 = False
c1_miss = True
if c1:
    dc1 = c1["P"] - c1["b0"]
    expect(dc1 <= 3 * S, f"B3f C1 (LZ4, N=12): P-B0 <= 3S = 192 MiB (got {dc1 / MIB:.1f})")
    expect(not c1["blocked"], f"B3f C1 writers not blocked (dWOSA={c1['wosa']}, blocked-state dumps={c1['blocked_dumps']})")
    row5 = dc1 >= 9 * S
    c1_miss = (dc1 > 3 * S) or c1["blocked"]
if c2:
    dc2 = c2["P"] - c2["b0"]
    expect(dc2 < 64 * MIB, f"B3f C2 (mmap): P-B0 < 64 MiB (got {dc2 / MIB:.1f}); mapped {c2['mapped0'] / MIB:.0f}->{c2['mapped_max'] / MIB:.0f} MiB")
    row6 = dc2 >= 64 * MIB
print(f"# summary: {n_pass} PASS, {n_fail} FAIL")
if row2:
    print("MATCHED B3g row 2 (claim wrong: buffers escape the cap)")
elif row3:
    print("MATCHED B3g row 3 (claim wrong: something other than N bounds the buffers)")
elif row4:
    print("MATCHED B3g row 4 (limit not reached: not confirmed)")
elif row5:
    print("MATCHED B3g row 5 (C1 near 12 S: re-examine; not confirmed)")
elif row1:
    print("MATCHED B3g row 1 (claim confirmed)" + (" - but C1 prediction missed: at most Partial (M8)" if c1_miss else ""))
else:
    print("MATCHED B3g: no matching row -> Not confirmed (no matching row)")
if row6:
    print("ALSO B3g row 6: C2 shows direct growth (A3 step 8c wrong)")
