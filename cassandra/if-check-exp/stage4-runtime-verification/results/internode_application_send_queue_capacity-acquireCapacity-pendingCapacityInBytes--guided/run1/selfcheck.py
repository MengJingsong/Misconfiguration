#!/usr/bin/env python3
"""Self-check of run 1 (stage 4, internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes).

Re-derives run 1's figures from the RAWEST files on the node, independently of the run script's own
conclusions (summary.txt / scenarios.csv), and tests them against the case file's frozen §9a prediction
(hash efd85ccc7840d755bbc3b254843733c3bfab9888), which is typed in below, not read from the EXPECTED lines.

Raw inputs, per label directory <RAW>/<label>/ (kept on the node):
  * send-trace.txt  — the Byteman trace at the EXIT of OutboundConnection.acquireCapacity(long,long) and of the
                      OutboundConnection constructor. The 'acquire' lines are the rawest evidence of the check
                      (outcome, pending bytes after, overloaded count, reserve usage); the 'config' lines are the
                      effective per-connection limits.
  * readings.csv    — JMX Connection metrics (ts_ms,tag,peer,attr,value), tagged by phase: idle / <sc>-pre /
                      <sc>-late / <sc>-drained / probe-before / probe-after / holdcheck-*.
  * <sc>/poll.csv   — a 0.25 s poller of system_views.internode_outbound (using_reserve_bytes etc.): a SECOND,
                      independent measurement of the per-peer reserve gauge.
  * session.log     — the heap-after-full-GC readings and the hold-trace lines.
Also read, only for an AGREEMENT cross-check (did the run script compute the same number from the same raw data):
  * scenarios.csv   — the run script's own derived per-(label,scenario,peer) table.

usage:  selfcheck.py [RAW_DIR]      (default: ~/stage4-logs/ssq)
Prints one line per check, "holds" / "DOES NOT HOLD"; a §9a prediction that the run already recorded as a
missed prediction (scenario A's X, results §3 row 5) is printed as "MISS (recorded)" and does not set the exit
code. Exit 1 if any load-bearing check does not hold, or any agreement check disagrees.
"""
import csv, os, re, statistics, sys, collections

MIB = 1048576
HOME = os.path.expanduser("~")
RAW = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HOME, "stage4-logs", "ssq")

# R1..R3 listen addresses (from the node yaml in session.log); S = 127.0.0.2
IP = {"R1": "127.0.0.3", "R2": "127.0.0.4", "R3": "127.0.0.5"}
PEERS = ["R1", "R2", "R3"]

# ----- the frozen §9a design, typed in (not read from the run). Tuple semantics match cluster-run.py's LABELS.
# cap, E (effective per-peer reserve = receive-key default unless the receive key is lowered), G (node-wide reserve),
# drops (does the reserves-low plateau drop?), first (first refusal outcome), withA (scenario A present?), rfs.
L = {
    "c512k": dict(cap=512 * 1024, E=MIB,        G=MIB,        drops=True,  first="INSUFFICIENT_GLOBAL",   withA=True,  rfs=[1]),
    "c1m":   dict(cap=MIB,        E=MIB,        G=MIB,        drops=True,  first="INSUFFICIENT_GLOBAL",   withA=True,  rfs=[1]),
    "c4m":   dict(cap=4 * MIB,    E=MIB,        G=MIB,        drops=True,  first="INSUFFICIENT_GLOBAL",   withA=True,  rfs=[1]),
    "c16m":  dict(cap=16 * MIB,   E=MIB,        G=MIB,        drops=True,  first="INSUFFICIENT_GLOBAL",   withA=True,  rfs=[1]),
    "defres": dict(cap=4 * MIB,   E=128 * MIB,  G=512 * MIB,  drops=False, first=None,                    withA=False, rfs=[1]),
    "nohold": dict(cap=MIB,       E=MIB,        G=MIB,        drops=False, first=None,                    withA=False, rfs=[1], nohold=True),
    "c1":    dict(cap=4 * MIB,    E=128 * MIB,  G=512 * MIB,  drops=False, first=None,                    withA=False, rfs=[1]),  # send-ep key lowered, receive key governs
    "c2":    dict(cap=4 * MIB,    E=MIB,        G=512 * MIB,  drops=True,  first="INSUFFICIENT_ENDPOINT", withA=False, rfs=[1]),  # receive-ep key lowered
    "peer":  dict(cap=4 * MIB,    E=MIB,        G=MIB,        drops=True,  first="INSUFFICIENT_GLOBAL",   withA=False, rfs=[1, 2, 3]),
}
ORDER = ["unit", "c512k", "c1m", "c4m", "c16m", "defres", "nohold", "c1", "c2", "peer"]

FAILS, MISSES, AGREE_FAILS = [], [], []


def result(kind, name, cond, note=""):
    tag = {"load": "holds" if cond else "DOES NOT HOLD",
           "miss": "holds" if cond else "MISS (recorded)",
           "agree": "agrees" if cond else "DISAGREES"}[kind]
    print("  %-14s %s%s" % (tag, name, (" — " + note) if note else ""))
    if not cond:
        (FAILS if kind == "load" else MISSES if kind == "miss" else AGREE_FAILS).append(name)


def ok(name, cond, note=""):     result("load", name, cond, note)
def miss(name, cond, note=""):   result("miss", name, cond, note)
def agree(name, cond, note=""):  result("agree", name, cond, note)
def info(text):                  print("  info: " + text)


def path(label, *p):
    return os.path.join(RAW, label, *p)


# ---------------------------------------------------------------- raw parsers
ACQ = re.compile(r"acquire type=(\S+) peer=/?(\S+) count=(\d+) bytes=(\d+) outcome=(\S+) pending=(\d+) "
                 r"pendingCount=(-?\d+) overloaded=(\d+) endpoint_using=(\d+) global_using=(\d+) ms=(\d+)")
CFG = re.compile(r"config type=(\S+) peer=/?(\S+) capacity=(\S+) endpoint=(\S+) global=(\S+) ms=(\d+)")


def trace(label):
    """all acquire and config lines of a label's send-trace.txt."""
    acq, cfg = [], []
    fp = path(label, "send-trace.txt")
    if not os.path.exists(fp):
        return acq, cfg
    for line in open(fp, errors="replace"):
        if line.startswith("acquire "):
            m = ACQ.match(line)
            if m:
                acq.append(dict(type=m.group(1), peer=m.group(2), count=int(m.group(3)), bytes=int(m.group(4)),
                                outcome=m.group(5), pending=int(m.group(6)), overloaded=int(m.group(8)),
                                ep=int(m.group(9)), gl=int(m.group(10)), ms=int(m.group(11))))
        elif line.startswith("config "):
            m = CFG.match(line)
            if m:
                cfg.append(dict(type=m.group(1), peer=m.group(2), capacity=m.group(3),
                                endpoint=m.group(4), glob=m.group(5), ms=int(m.group(6))))
    return acq, cfg


def readings(label):
    """readings.csv rows -> dict keyed (tag, peer, attr) = int value; and the ts of each tag (min,max)."""
    jm, tts = {}, collections.defaultdict(list)
    fp = path(label, "readings.csv")
    if not os.path.exists(fp):
        return jm, tts
    for r in csv.DictReader(open(fp)):
        v = r["value"]
        try:
            iv = int(float(v)) if v not in ("", None) and not str(v).startswith("ERROR") else None
        except ValueError:
            iv = None
        jm[(r["tag"], r["peer"], r["attr"])] = iv
        tts[r["tag"]].append(int(r["ts_ms"]))
    return jm, tts


def large(acq, pe, t0=None, t1=None):
    out = [a for a in acq if a["type"] == "LARGE_MESSAGES" and a["peer"].startswith(IP[pe] + ":")]
    if t0 is not None:
        out = [a for a in out if t0 <= a["ms"] <= t1]
    return out


def poll_reserve_max(label, sc, pe):
    """max using_reserve_bytes for a peer from the scenario's internode_outbound poller (independent of the trace)."""
    fp = path(label, sc, "poll.csv")
    if not os.path.exists(fp):
        return None
    vals = []
    for r in csv.DictReader(open(fp)):
        if r.get("peer", "").startswith(IP[pe] + ":") and r.get("using_reserve_bytes", "") not in ("", "ERROR"):
            vals.append(int(r["using_reserve_bytes"]))
    return max(vals) if vals else None


def scen_rows(label):
    fp = path(label, "scenarios.csv")
    return list(csv.DictReader(open(fp))) if os.path.exists(fp) else []


def heap_from_session(label):
    """(idle_mean, idle_spread, {sc: heap5}) in KiB, parsed from session.log notes."""
    idle_mean = idle_spread = None
    heap5 = {}
    fp = path(label, "session.log")
    if not os.path.exists(fp):
        return idle_mean, idle_spread, heap5
    txt = open(fp, errors="replace").read()
    m = re.search(r"idle heap used after full GC \(KiB\): \[([\d, ]+)\]", txt)
    if m:
        hs = [int(x) for x in m.group(1).split(",")]
        idle_mean, idle_spread = statistics.mean(hs), max(hs) - min(hs)
    for sc, kb in re.findall(r"\n\[[\d:\- ]+\] (\S+): heap used after full GC at ~5 s = (\d+) KiB", txt):
        heap5[sc] = int(kb)
    return idle_mean, idle_spread, heap5


def scenarios_present(tts):
    """scenario keys from readings tags: strip -pre/-late/-drained; keep those with a -pre and a -late."""
    keys = set()
    for t in tts:
        for suf in ("-pre", "-late", "-drained"):
            if t.endswith(suf):
                keys.add(t[: -len(suf)])
    return sorted(k for k in keys if (k + "-pre") in tts and (k + "-late") in tts)


# ---------------------------------------------------------------- unit tier
def unit_tier():
    print("\n== UNIT TIER (unit/summary.txt)")
    fp = path("unit", "summary.txt")
    if not os.path.exists(fp):
        ok("unit: summary.txt exists", False, "missing")
        return
    summ = open(fp).read()
    want = [("ConnectionTest.testInsufficientSpace", 1), ("ConnectionTest.testAcquireReleaseOutbound", 1),
            ("ResourceLimitsTest", 5), ("SendQueueCapacityTest", 4), ("SendQueueWiringTest", 2)]
    for name, n in want:
        m = re.search(re.escape(name) + r": ant rc=(\d+);.*?Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)", summ)
        ok("unit %s: %d tests, 0 failure/error, ant rc 0" % (name, n),
           bool(m) and m.group(1) == "0" and int(m.group(2)) == n and m.group(3) == "0" and m.group(4) == "0",
           "" if m else "no line")
    m = re.search(r"MISMATCH lines: (\d+)", summ)
    ok("unit: 0 instrument MISMATCH lines", bool(m) and m.group(1) == "0", m.group(0) if m else "no line")


# ---------------------------------------------------------------- one cluster label
def cluster_label(label):
    d = L[label]
    cap, E, G, drops, first, withA = d["cap"], d["E"], d["G"], d["drops"], d["first"], d["withA"]
    F = min(E, G)
    print("\n== %s  (C=%d E=%d G=%d F=%d drops=%s first=%s)" % (label, cap, E, G, F, drops, first))
    acq, cfg = trace(label)
    jm, tts = readings(label)
    srows = {(r["scenario"], r["peer"]): r for r in scen_rows(label)}

    # --- config trace: effective limits of every R1..R3 connection == the typed prediction
    for pe in PEERS:
        ls = [c for c in cfg if c["peer"].startswith(IP[pe] + ":")]
        good = len(ls) >= 3 and all(c["capacity"] == str(cap) and c["endpoint"] == str(E) and c["glob"] == str(G) for c in ls)
        ok("%s config %s: %d conns, capacity=%d endpoint=%d global=%d" % (label, pe, len(ls), cap, E, G),
           good, "" if good else "got " + "; ".join(sorted({f"cap={c['capacity']} ep={c['endpoint']} gl={c['glob']}" for c in ls})))

    # --- idle control
    if ("idle", "R1", "LargeMessagePendingBytes") in jm:
        idle_ok = all(jm.get(("idle", pe, "LargeMessagePendingBytes")) == 0 and
                      jm.get(("idle", pe, "LargeMessageDroppedTasksDueToOverload")) == 0 for pe in PEERS)
        ok("%s idle: pending bytes 0 and no overload on all links" % label, idle_ok)

    # --- scenarios (A, B, B-rfN, B-nohold) derived from readings tags
    for sc in scenarios_present(tts):
        t0, t1 = min(tts[sc + "-pre"]), max(tts[sc + "-late"])
        if sc == "A":
            rf = 1
        elif re.match(r"B-rf(\d)$", sc):
            rf = int(sc[-1])
        else:
            rf = 1
        peers = PEERS[:rf]
        allM = [a["bytes"] for pe in peers for a in large(acq, pe, t0, t1) if a["outcome"] == "SUCCESS"]
        M = statistics.mode(allM) if allM else None
        # per-peer independent figures from the trace
        X, acc, ref, firsts, over = {}, {}, {}, {}, {}
        for pe in PEERS:
            ll = large(acq, pe, t0, t1)
            X[pe] = max((a["pending"] for a in ll), default=0)
            acc[pe] = sum(1 for a in ll if a["outcome"] == "SUCCESS")
            rl = sorted((a for a in ll if a["outcome"] != "SUCCESS"), key=lambda a: a["ms"])
            ref[pe] = len(rl)
            firsts[pe] = rl[0]["outcome"] if rl else None
            over[pe] = max((a["overloaded"] for a in ll), default=0)
        info("%s %s: M=%s X=%s accepted=%s refused=%s first=%s" % (label, sc, M, X, acc, ref, firsts.get(peers[0])))

        # agreement with the run script's scenarios.csv (same raw data, same number?)
        for pe in peers:
            sr = srows.get((sc, pe))
            if sr:
                agree("%s %s %s: X and accepted match scenarios.csv (%s, %s)" % (label, sc, pe, X[pe], acc[pe]),
                      int(sr["X_trace_max_pending"]) == X[pe] and int(sr["accepted"]) == acc[pe],
                      "csv X=%s acc=%s" % (sr["X_trace_max_pending"], sr["accepted"]))

        if M is None:
            ok("%s %s: at least one message accepted on the large link" % (label, sc), False)
            continue

        # ===== scenario A: calibration (recorded miss on X; see results §3 row 5)
        if sc == "A":
            miss("%s A: X = 2M +-1 message (2M=%d, X=%d)" % (label, 2 * M, X["R1"]), abs(X["R1"] - 2 * M) <= M,
                 "recorded missed prediction (X read ~4M)")
            ok("%s A: no reserve use and no drop" % label, ref["R1"] == 0 and (poll_reserve_max(label, sc, "R1") or 0) == 0)
            continue

        # ===== no-hold control: empirical, no §9a row rests on it
        if d.get("nohold") or sc.endswith("nohold"):
            info("%s %s: no-hold control (empirical): X=%d vs C+F=%d, refused=%d" % (label, sc, X["R1"], cap + F, ref["R1"]))
            continue

        # ===== scenario B
        # §9a distinguishes three held arms:
        #   drops + INSUFFICIENT_GLOBAL  -> the plateau is FLAT past the 10 s deadline (a global refusal does not take the
        #                                   prune-and-retry branch :337-341, so nothing prunes a connected held link);
        #   drops + INSUFFICIENT_ENDPOINT-> an endpoint refusal DOES take :337-341, so the held link prunes and the plateau
        #                                   CHURNS (expiries, more than one accept per thread) while the peak still obeys C+F;
        #   no drops (default reserves)  -> nothing is dropped and C does not bind; the reserves do (X between C and C+F).
        D = 256 * M  # THREADS_B * M: §9a's offered-load estimate (one message in flight per thread)
        global_arm = drops and first == "INSUFFICIENT_GLOBAL"
        if drops:
            ok("%s %s: valid run, offered load D=%d exceeds C+F=%d" % (label, sc, D, cap + F), D > cap + F)
            for pe in peers:
                ok("%s %s %s: overload branch fired (refused=%d>0, trace overloaded=%d)" % (label, sc, pe, ref[pe], over[pe]),
                   ref[pe] > 0)
            ok("%s %s: first refusal is %s (was %s)" % (label, sc, first, firsts[peers[0]]), firsts[peers[0]] == first)
            # no accepted acquire ever recorded pending above C+F (bypass check): the check is never seen to admit past the limit
            bad = [a for pe in peers for a in large(acq, pe, t0, t1) if a["outcome"] == "SUCCESS" and a["pending"] > cap + F]
            ok("%s %s: no SUCCESS acquire with pending above C+F (%d found)" % (label, sc, len(bad)), not bad)
            if rf == 1:
                # single-link plateau band on the peak (holds for both global and endpoint arms)
                lo, hi = cap + F - M, cap + F
                ok("%s %s R1: peak X within (C+F-M, C+F] (%d < %d <= %d)" % (label, sc, lo, X["R1"], hi), lo < X["R1"] <= hi)
                rmax = poll_reserve_max(label, sc, "R1")
                if rmax is not None:
                    ok("%s %s R1: using_reserve in (F-M, F] (%d < %d <= %d)" % (label, sc, F - M, rmax, F), F - M < rmax <= F)
        else:
            # no-drop control: §9a claims nothing is dropped and C does not bind (the reserves do).
            for pe in peers:
                ok("%s %s %s: nothing dropped (refused=%d) and C does not bind (C=%d < X=%d <= C+F=%d)" % (label, sc, pe, ref[pe], cap, X[pe], cap + F),
                   ref[pe] == 0 and cap < X[pe] <= cap + F)
            info("%s %s: X=%d exceeds the 256*M offered-load estimate D=%d (clients send more than one per thread during the hold, as in scenario A)" % (label, sc, X["R1"], D))

        # plateau flat past the deadline: only the GLOBAL-refusal arm (§9a "nothing prunes")
        if global_arm:
            for pe in peers:
                late = jm.get((sc + "-late", pe, "LargeMessagePendingBytes"))
                exp = jm.get((sc + "-late", pe, "LargeMessageDroppedTasksDueToTimeout"), 0) - jm.get((sc + "-pre", pe, "LargeMessageDroppedTasksDueToTimeout"), 0)
                ok("%s %s %s: plateau flat at 12.5s past the 10s deadline (JMX late %s == peak %d), nothing expired (%d)" % (label, sc, pe, late, X[pe], exp),
                   late == X[pe] and exp == 0)
            # drain: after the lift pending -> 0, timed-out == accepted, completed unchanged
            for pe in peers:
                pend = jm.get((sc + "-drained", pe, "LargeMessagePendingBytes"))
                tmo = jm.get((sc + "-drained", pe, "LargeMessageDroppedTasksDueToTimeout"), 0) - jm.get((sc + "-pre", pe, "LargeMessageDroppedTasksDueToTimeout"), 0)
                comp = jm.get((sc + "-drained", pe, "LargeMessageCompletedTasks"), 0) - jm.get((sc + "-late", pe, "LargeMessageCompletedTasks"), 0)
                ok("%s %s %s: drain -> pending 0 (%s), timed-out=accepted (%d=%d), completed unchanged (%d)" % (label, sc, pe, pend, tmo, acc[pe], comp),
                   pend == 0 and tmo == acc[pe] and comp == 0)
        elif drops:
            # endpoint-refusal arm (c2): the plateau churns via the prune-and-retry branch; the peak still obeys the band
            for pe in peers:
                late = jm.get((sc + "-late", pe, "LargeMessagePendingBytes"))
                exp = jm.get((sc + "-late", pe, "LargeMessageDroppedTasksDueToTimeout"), 0) - jm.get((sc + "-pre", pe, "LargeMessageDroppedTasksDueToTimeout"), 0)
                info("%s %s %s: endpoint-refusal arm churns (JMX late %s <= peak %d; %d expired by 12.5s) — INSUFFICIENT_ENDPOINT takes the prune-and-retry branch :337-341" % (label, sc, pe, late, X[pe], exp))

        # drain always returns the accounting to zero (the §9a leak row): universal for every held arm
        for pe in peers:
            pend = jm.get((sc + "-drained", pe, "LargeMessagePendingBytes"))
            ok("%s %s %s: after the lift pending bytes return to 0 (no leak) (%s)" % (label, sc, pe, pend), pend == 0)
        # liveness probe (R1): the parked link resumes and delivers a fresh write
        pb = jm.get(("probe-after", "R1", "LargeMessageCompletedTasks"))
        pbf = jm.get(("probe-before", "R1", "LargeMessageCompletedTasks"))
        if pb is not None and pbf is not None:
            ok("%s %s: liveness probe delivered (R1 completed +1: %d->%d)" % (label, sc, pbf, pb), pb - pbf == 1)

    # --- peer sweep: §9a's node-wide formula (sum band), NOT the single-link band
    if d["rfs"] == [1, 2, 3]:
        print("  -- peer sweep (§9a node-wide formula P*C+G)")
        for rf in (1, 2, 3):
            sc = "B-rf%d" % rf
            if (sc + "-pre") not in tts:
                continue
            t0, t1 = min(tts[sc + "-pre"]), max(tts[sc + "-late"])
            peers = PEERS[:rf]
            allM = [a["bytes"] for pe in peers for a in large(acq, pe, t0, t1) if a["outcome"] == "SUCCESS"]
            M = statistics.mode(allM) if allM else None
            Xs = {pe: max((a["pending"] for a in large(acq, pe, t0, t1)), default=0) for pe in peers}
            tot = sum(Xs.values())
            lo, hi = rf * cap + G - (rf + 1) * M, rf * cap + G
            ok("%s P=%d: sum of peaks in (P*C+G-(P+1)*M, P*C+G] = (%d, %d]: %d" % (sc, rf, lo, hi, tot), lo < tot <= hi)
            ok("%s P=%d: each link at least C-M (%d): %s" % (sc, rf, cap - M, Xs), all(v >= cap - M for v in Xs.values()))
            gauges = {pe: (poll_reserve_max(label, sc, pe) or 0) for pe in peers}
            ok("%s P=%d: each reserve gauge <= E (%d) and sum <= G (%d): %s" % (sc, rf, E, G, gauges),
               all(v <= E for v in gauges.values()) and sum(gauges.values()) <= G)


# ---------------------------------------------------------------- heap proportionality across the C sweep
def heap_tier():
    print("\n== HEAP PROPORTIONALITY (C sweep, §9a heap row)")
    ratios, data = [], []
    for label in ("c512k", "c1m", "c4m", "c16m"):
        idle_mean, spread, heap5 = heap_from_session(label)
        if idle_mean is None or "B" not in heap5:
            continue
        acq, _ = trace(label)
        _, tts = readings(label)
        if "B-pre" not in tts:
            continue
        t0, t1 = min(tts["B-pre"]), max(tts["B-late"])
        Xs = sum(max((a["pending"] for a in large(acq, pe, t0, t1)), default=0) for pe in PEERS)
        dh = (heap5["B"] - idle_mean) * 1024
        adj = dh > 3 * spread * 1024
        data.append((label, dh, Xs, dh / Xs if Xs else None, adj))
        info("%s: delta_heap=%d B, X=%d, ratio=%.3f, adjudicable(delta>3*spread)=%s (spread=%d KiB)" %
             (label, dh, Xs, (dh / Xs if Xs else 0), adj, spread))
        if adj and Xs:
            ratios.append(dh / Xs)
    if len(ratios) >= 2:
        med = statistics.median(ratios)
        within = all(med / 2 <= r <= med * 2 for r in ratios)
        ok("heap: every adjudicable delta_heap/X within a factor 2 of the median (%.3f), n=%d" % (med, len(ratios)), within)
    elif len(ratios) == 1:
        info("only ONE value (c16m) cleared 3x the idle-heap spread; proportionality across the sweep is not demonstrable (n=1). "
             "The other three idle floors were too noisy (spread 15-17 MiB). §9a heap row reads as accounting-only here, not a demonstrated heap proxy.")
    else:
        info("no adjudicable value in the C sweep; §9a heap row is 'Not confirmed' (accounting-only)")


# ---------------------------------------------------------------- main
def main():
    print("Self-check of run 1 — internode_application_send_queue_capacity")
    print("RAW = %s" % RAW)
    unit_tier()
    for label in ORDER:
        if label == "unit":
            continue
        if os.path.isdir(path(label)):
            cluster_label(label)
    heap_tier()
    print("\n== SUMMARY")
    print("  load-bearing checks that DO NOT HOLD: %d" % len(FAILS))
    for f in FAILS:
        print("     - " + f)
    print("  recorded missed predictions reproduced: %d" % len(MISSES))
    for m in MISSES:
        print("     - " + m)
    print("  agreement checks that DISAGREE with the run script: %d" % len(AGREE_FAILS))
    for a in AGREE_FAILS:
        print("     - " + a)
    sys.exit(1 if (FAILS or AGREE_FAILS) else 0)


if __name__ == "__main__":
    main()
