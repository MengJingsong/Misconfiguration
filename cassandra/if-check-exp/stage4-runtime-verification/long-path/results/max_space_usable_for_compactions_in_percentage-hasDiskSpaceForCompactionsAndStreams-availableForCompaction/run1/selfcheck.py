#!/usr/bin/env python3
"""Self-check of run 1 (stage 4, max_space_usable_for_compactions_in_percentage).

Re-derives the run's figures from raw files instead of reading the run script's own conclusions:
  * the node's raw debug.log and system.log of each label (kept on the node, copied to RAW_DIR), and
  * the excerpts next to this file: cluster/<label>/{summary.txt,passes.csv,triggers.csv,samples.csv}, unit/*.
The expected values are the case file's 9a prediction (n = 0, 0, 2, 5, abort; I2 n = 5; H1 refused; H2 in full), typed
in below, not read from the run script's EXPECTED lines.

usage:  selfcheck.py RAW_DIR        (RAW_DIR/<label>/debug.log and system.log, labels d95 f15 f08 f04 f01 inflight)
Prints one line per check, "holds" or "DOES NOT HOLD"; exit code 1 if any does not hold.
"""
import csv, datetime, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = sys.argv[1]
MIB = 1048576
FLOOR = 50 * MIB
FAILS = []


def ok(name, cond, note=""):
    print("%-14s %s%s" % ("holds" if cond else "DOES NOT HOLD", name, (" — " + note) if note else ""))
    if not cond:
        FAILS.append(name)


def info(text):
    print("  info: " + text)


def java_round(x):
    return int(math.floor(x + 0.5))


def epoch(d, t, ms):
    dt = datetime.datetime.strptime(d + " " + t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    return dt.timestamp() + int(ms) / 1000.0


def ladder(lengths, budget, extra=0):
    """The 9e simulation: drop the largest input while the rest does not fit; abort at one input.
    Returns (requested per pass, number dropped, aborted)."""
    cur = sorted(lengths)
    passes = []
    while True:
        r = sum(cur) + extra
        passes.append(r)
        if r <= budget:
            return passes, len(lengths) - len(cur), False
        if len(cur) == 1:
            return passes, len(lengths) - 1, True
        cur.remove(max(cur))


def read(path):
    with open(path) as f:
        return f.read()


def rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------- raw log parsers
DBG = re.compile(r"^DEBUG\s+\[([^\]]+)\]\s+(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d{3}) Directories\.java:550 - "
                 r"FileStore (\S+) \(([^)]*)\) has (\d+) bytes available, checking if we can write (\d+) bytes")
TS = re.compile(r"(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d{3})")
UNITS = {"B": 1, "KiB": 1024, "MiB": MIB, "GiB": MIB * 1024}


def debug_lines(label):
    out = []
    for line in open(os.path.join(RAW, label, "debug.log"), errors="replace"):
        m = DBG.match(line)
        if m and int(m.group(8)) >= MIB:          # the harness keeps requested >= 1 MiB (9d): system tables stay out
            out.append(dict(thread=m.group(1), ts=epoch(m.group(2), m.group(3), m.group(4)), store=m.group(5),
                            dev=m.group(6), avail=int(m.group(7)), req=int(m.group(8))))
    return out


def groups(lines):
    gs = []
    for l in lines:
        if gs and gs[-1][-1]["thread"] == l["thread"] and l["ts"] - gs[-1][-1]["ts"] < 2.0:
            gs[-1].append(l)
        else:
            gs.append([l])
    return gs


def syslog(label):
    ev = dict(reducing=[], abortwarn=[], hasonly=[], disabled=[], compacting=[], compacted=[], config=None, jvm=None,
              errors=[])
    prev_error_ts = None
    for line in open(os.path.join(RAW, label, "system.log"), errors="replace"):
        m = TS.search(line)
        ts = epoch(*m.groups()) if m else None
        # an abort is an ERROR line (JVMStabilityInspector, "Exception in thread") followed by the exception's line
        if line.startswith("java.lang.RuntimeException: Not enough space for compaction") and prev_error_ts:
            ev["errors"].append(prev_error_ts)
        prev_error_ts = ts if line.startswith("ERROR") else None
        if "CompactionTask.java:446 - Not enough space for compaction" in line and "Reducing scope" in line:
            ev["reducing"].append(ts)
        elif "CompactionTask.java:440 - Not enough space for compaction (" in line:
            ev["abortwarn"].append(ts)
        elif "Directories.java:553 - FileStore" in line and "has only" in line:
            ev["hasonly"].append(ts)
        elif "Compaction space check is disabled" in line:
            ev["disabled"].append(ts)
        elif "CompactionTask.java:175 - Compacting (" in line and "/ks1/" in line:
            ev["compacting"].append((ts, line.count("-Data.db")))
        elif "CompactionTask.java:274 - Compacted (" in line and "/ks1/" in line:
            c = re.search(r"Compacted \([^)]+\) (\d+) sstables to \[[^\]]*\] to level=\d+\.\s+([\d.,]+)(B|KiB|MiB|GiB) "
                          r"to ([\d.,]+)(B|KiB|MiB|GiB)", line)
            if c:
                ev["compacted"].append((ts, int(c.group(1)),
                                        float(c.group(2).replace(",", "")) * UNITS[c.group(3)],
                                        float(c.group(4).replace(",", "")) * UNITS[c.group(5)]))
        if "Node configuration:[" in line and ev["config"] is None:
            ev["config"] = line
        if "JVM Arguments:" in line and ev["jvm"] is None:
            ev["jvm"] = line
    return ev


def in_window(times, g, pad=1.0):
    return [t for t in times if g[0]["ts"] - pad <= t <= g[-1]["ts"] + pad]


def summary_facts(label):
    txt = read(os.path.join(HERE, "cluster", label, "summary.txt"))
    ds = {}
    for t, lens in re.findall(r"DATASET ks1\.(\w+): Data\.db lengths \[([\d, ]+)\]", txt):
        ds[t] = [int(x) for x in lens.split(",")]
    m = re.search(r"PLAN U (\d+) \(node stopped\);.*? pct (default|[0-9.eE+-]+);", txt)
    pct = 0.95 if m.group(2) == "default" else float(m.group(2))
    return ds, pct, txt


def trig(label):
    return {r["arm"]: r for r in rows(os.path.join(HERE, "cluster", label, "triggers.csv"))}


def samples(label):
    out = []
    for r in rows(os.path.join(HERE, "cluster", label, "samples.csv")):
        out.append(r)
    return out


def interp(series, t):
    """series: sorted list of (t, value); linear interpolation."""
    for (t0, v0), (t1, v1) in zip(series, series[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v0
    return None


# ---------------------------------------------------------------- unit tier
def unit_tier():
    print("\n== UNIT TIER (unit/summary.txt, unit/run.out)")
    summ = read(os.path.join(HERE, "unit", "summary.txt"))
    want = [("DirectoriesTest", 42), ("CompactionsBytemanTest", 6), ("PartialCompactionsTest", 1),
            ("CompactionBudgetTest", 1), ("CompactionLadderTest", 1)]
    for name, n in want:
        m = re.search(name + r": ant rc=(\d+); .*?Tests run: (\d+), Failures: (\d+), Errors: (\d+)", summ)
        ok("unit %s: %d tests, no failure or error, ant rc 0" % (name, n),
           bool(m) and m.group(1) == "0" and int(m.group(2)) == n and m.group(3) == "0" and m.group(4) == "0",
           m.group(0)[:20] + "…" if m else "no line")
    out = read(os.path.join(HERE, "unit", "run.out"))
    checks = re.findall(r"^STAGE4 check (\S+) (\S+) (\S+) (\w+)$", out, re.M)
    bad = [c for c in checks if c[3] != "ok"]
    ok("unit: every STAGE4 check line is ok (%d lines), no MISMATCH" % len(checks),
       len(checks) > 0 and not bad and "MISMATCH" not in out, "bad: %s" % bad[:3] if bad else "")
    ok("unit: two 'STAGE4 summary mismatches 0' lines (one per new test)",
       len(re.findall(r"^STAGE4 summary mismatches 0$", out, re.M)) == 2)
    pc = {m[0]: (m[1], m[2]) for m in re.findall(r"^STAGE4 check (f[\d.]+)_pass_count (\S+) (\S+) ok$", out, re.M)}
    # 9a prediction at B/total = 1.5, 0.8, 0.4, 0.1: passes 1, 3, 6, 8 (n = 0, 2, 5, abort after 7 drops)
    for f, passes in (("f1.5", 1), ("f0.8", 3), ("f0.4", 6), ("f0.1", 8)):
        ok("unit ladder %s: %d passes (predicted by 9a), observed = expected in the test" % (f, passes),
           pc.get(f) == (str(passes), str(passes)), str(pc.get(f)))
    info("budget arithmetic (CompactionBudgetTest): " +
         "; ".join(re.findall(r"STAGE4 info (_pct[\d.]+ B=\d+)", out)))


# ---------------------------------------------------------------- cluster tier
PRED = {   # 9a prediction by label and arm: number of inputs dropped, 'abort', or 'bypass'
    "d95": {"A": 0}, "f15": {"A": 0}, "f08": {"B": 2}, "f04": {"B": 5},
    "f01": {"C": "abort", "H1": "abort", "H2": "bypass"}, "inflight": {"I1": 0, "I2": 5}}
BTOTAL = {"d95": None, "f15": 1.5, "f08": 0.8, "f04": 0.4, "f01": 0.1, "inflight": 1.4}


def check_label(label):
    print("\n== %s" % label.upper())
    ds, pct, txt = summary_facts(label)
    tr = trig(label)
    dl = debug_lines(label)
    ev = syslog(label)
    gs = groups(dl)
    t_lens = ds["t"]
    total = sum(t_lens)

    # ---- the knob took effect, and the hold-fixed settings (9b)
    cfg = ev["config"] or ""
    pcfg = re.search(r"max_space_usable_for_compactions_in_percentage=([0-9.eE+-]+)", cfg)
    ok("%s: the node's own start-up configuration line shows max_space_usable_for_compactions_in_percentage = %s"
       % (label, pct), bool(pcfg) and abs(float(pcfg.group(1)) - pct) < 1e-12, pcfg.group(1) if pcfg else "no line")
    ok("%s: min_free_space_per_drive 50MiB, compaction_throughput 64MiB/s, concurrent_compactors default (null)" % label,
       "min_free_space_per_drive=50MiB" in cfg and "compaction_throughput=64MiB/s" in cfg
       and "concurrent_compactors=null" in cfg)
    jvm = ev["jvm"] or ""
    ok("%s: JVM -Xms4G -Xmx4G" % label, "-Xms4G" in jvm and "-Xmx4G" in jvm)
    ok("%s: every checked file store is /mnt/stage4-data (/dev/loop0), the dedicated filesystem" % label,
       all(l["store"] == "/mnt/stage4-data" and l["dev"] == "/dev/loop0" for l in dl) and len(dl) > 0)
    ok("%s: dataset: 8 Data.db files per table, largest <= 1.10 x smallest, each within 10%% of 64 MiB, payload "
       "incompressible (Data.db >= 12,800 x 5,120 B)" % label,
       all(len(v) == 8 and max(v) <= 1.10 * min(v) and all(abs(x - 64 * MIB) <= 0.10 * 64 * MIB for x in v)
           and all(x >= 12800 * 5120 for x in v) for v in ds.values()),
       "tables %s, spread %s" % (sorted(ds), ["%.5f" % (max(v) / min(v)) for v in ds.values()]))

    arms = PRED[label]
    if label in ("d95", "f15", "f08", "f04"):
        arm = list(arms)[0]
        g = gs[0]
        ok("%s: exactly one burst of table-size check lines in the raw debug.log (no other compaction >= 1 MiB)"
           % label, len(gs) == 1, "%d burst(s), %d lines" % (len(gs), len(dl)))
        U = int(tr[arm]["U_before"])
        B = java_round((U - FLOOR) * pct)
        ok("%s: every pass's `available` = round((U - 50 MiB) x pct) = %d recomputed from df %d and the config value"
           % (label, B, U), all(abs(l["avail"] - B) <= 1 for l in g), "available %s" % sorted({l["avail"] for l in g}))
        sim, dropped, aborted = ladder(t_lens, B)
        ok("%s: B / total = %.4f (intended %s)" % (label, B / float(total), BTOTAL[label] or "default 0.95, far above"),
           BTOTAL[label] is None and B / float(total) > 5 or abs(B / float(total) - BTOTAL[label]) < 1e-3)
        ok("%s: the raw pass lines' `requested` equal the ladder simulated from the Data.db lengths: %s"
           % (label, sim), [l["req"] for l in g] == sim)
        ok("%s: inputs dropped = %d (9a: %s)" % (label, dropped, arms[arm]),
           dropped == arms[arm] and not aborted and len(g) == dropped + 1)
        ok("%s: last pass is the first with requested <= available; every earlier one exceeds it" % label,
           g[-1]["req"] <= g[-1]["avail"] and all(l["req"] > l["avail"] for l in g[:-1]))
        red, hasonly = in_window(ev["reducing"], g), in_window(ev["hasonly"], g)
        ok("%s: system.log: `Reducing scope` x%d, `has only … but … is needed` x%d, abort warning x0, ERROR x0"
           % (label, dropped, dropped),
           len(red) == dropped and len(hasonly) == dropped and not in_window(ev["abortwarn"], g)
           and not in_window(ev["errors"], g))
        ok("%s: system.log: no 'Compaction space check is disabled' line" % label, not ev["disabled"])
        k = 8 - dropped
        c = ev["compacting"]
        d = ev["compacted"]
        ok("%s: one `Compacting` line of ks1 with %d input Data.db files; `Compacted … %d sstables`" % (label, k, k),
           len(c) == 1 and c[0][1] == k and len(d) == 1 and d[0][1] == k, "compacting %s compacted %s" % (c, d))
        kept = sum(sorted(t_lens)[:k])
        ok("%s: kept inputs %d B, output %.0f B in the Compacted line (within 0.01%%); inputs' total is the over-"
           "estimate of the output, the output <= B" % (label, kept, d[0][3] if d else -1),
           bool(d) and abs(d[0][3] - kept) <= 0.0001 * kept + 2048 and d[0][3] <= B,
           "output %.0f vs B %d" % (d[0][3], B) if d else "")
        # disk, from the 500 ms sampler
        ss = samples(label)
        du = [int(r["du_t"]) for r in ss]
        base, peak, fin = du[0], max(du), du[-1]
        ok("%s: sampler du of ks1.t: baseline %d, peak %d (rise %.4f x the kept inputs), final %d (the shed inputs "
           "stay: final within 0.01%% of baseline)" % (label, base, peak, (peak - base) / float(kept), fin),
           0.95 <= (peak - base) / float(kept) <= 1.05 and abs(fin - base) <= 0.0001 * base)
        r = tr[arm]
        ok("%s: files %s -> %s in triggers.csv = 1 output + %d shed inputs; nodetool rc 0" % (
            label, r["files_before"], r["files_after"], dropped),
           r["files_before"] == "8" and int(r["files_after"]) == 1 + dropped and r["rc"] == "0")
        ok("%s: counters (script's JMX read; raw values not kept): Reduced +%d, Dropped +%d, Aborted +0 — equals "
           "the log events (reducing lines %d)" % (label, 1 if dropped else 0, dropped, len(red)),
           int(r["reduced_delta"]) == (1 if dropped else 0) and int(r["dropped_delta"]) == dropped
           and int(r["aborted_delta"]) == 0 and len(red) == dropped)
        # idle control: the first 30 s of the sampler show nothing moving
        ok("%s: idle control: the sampler's first 60 rows (30 s) show du and df unchanged" % label,
           len({r["du_t"] for r in ss[:60]}) == 1 and len({r["avail"] for r in ss[:60]}) == 1)

    elif label == "f01":
        U = int(tr["C"]["U_before"])
        B = java_round((U - FLOOR) * pct)
        sim, dropped, aborted = ladder(t_lens, B)
        ok("f01: B = round((U - 50 MiB) x pct) = %d, B / total = %.4f; simulated: %d passes, abort = %s"
           % (B, B / float(total), len(sim), aborted), abs(B / float(total) - 0.1) < 1e-3 and aborted and len(sim) == 8)
        ok("f01: two bursts of check lines in the raw debug.log (C and H1), none for H2", len(gs) == 2, "%d" % len(gs))
        for name, g in zip(("C", "H1"), gs):
            ok("f01 %s: 8 pass lines, `available` = %d, `requested` = the simulated %s" % (name, B, sim),
               [l["req"] for l in g] == sim and all(abs(l["avail"] - B) <= 1 for l in g))
            ok("f01 %s: no pass is admitted (every requested > available): the ladder reaches one input and aborts"
               % name, all(l["req"] > l["avail"] for l in g))
            ok("f01 %s: system.log: `Reducing scope` x7, one abort warning (CompactionTask:440), `has only` x8, "
               "exactly one ERROR whose exception is the RuntimeException 'Not enough space for compaction'" % name,
               len(in_window(ev["reducing"], g)) == 7 and len(in_window(ev["abortwarn"], g)) == 1
               and len(in_window(ev["hasonly"], g)) == 8 and len(in_window(ev["errors"], g)) == 1,
               "errors in window %d, in the file %d" % (len(in_window(ev["errors"], g)), len(ev["errors"])))
            t = tr[name]
            ok("f01 %s: nodetool rc 2; files 8 -> 8 and Data.db total unchanged (%s = %d); counters +0/+0/+1"
               % (name, t["datadb_after_bytes"], total),
               t["rc"] == "2" and t["files_after"] == "8" and int(t["datadb_after_bytes"]) == total
               and (t["reduced_delta"], t["dropped_delta"], t["aborted_delta"]) == ("0", "0", "1"))
        ss = samples("f01")
        ts_ = [float(r["epoch"]) for r in ss]
        du = [int(r["du_t"]) for r in ss]
        base = du[0]
        lo, hi = gs[0][0]["ts"] - 1.0, gs[1][-1]["ts"] + 2.0
        ok("f01: sampler: du of ks1.t never rose above its baseline %d while C and H1 ran (no output written), "
           "so the refusal left the inputs alone" % base,
           all(d <= base for t_, d in zip(ts_, du) if lo <= t_ <= hi) and any(lo <= t_ <= hi for t_ in ts_))
        # H2
        h2 = tr["H2"]
        dis = ev["disabled"]
        ok("f01 H2: the info line 'Compaction space check is disabled' once, after H1's last pass line",
           len(dis) == 1 and dis[0] > gs[1][-1]["ts"])
        comp = [c for c in ev["compacting"] if c[0] >= dis[0] - 1.0] if dis else []
        done = [d for d in ev["compacted"] if dis and d[0] >= dis[0]]
        ok("f01 H2: one `Compacting` line with 8 input files after it; `Compacted … 8 sstables`",
           len(comp) == 1 and comp[0][1] == 8 and len(done) == 1 and done[0][1] == 8, "%s %s" % (comp, done))
        ok("f01 H2: no raw debug pass line (requested >= 1 MiB) from that task: after H1 nothing more in the raw "
           "debug.log, although the output is %.0f B against B = %d (%.1f x the budget)"
           % (done[0][3] if done else -1, B, (done[0][3] / B) if done else 0),
           len(dl) == 16 and bool(done) and done[0][3] > 10 * B)
        ok("f01 H2: Data.db files 8 -> 1; output %s B within 5%% of the inputs' %d; rc 0; counters +0/+0/+0"
           % (h2["datadb_after_bytes"], total),
           h2["files_before"] == "8" and h2["files_after"] == "1" and h2["rc"] == "0"
           and abs(int(h2["datadb_after_bytes"]) - total) <= 0.05 * total
           and (h2["reduced_delta"], h2["dropped_delta"], h2["aborted_delta"]) == ("0", "0", "0"))
        ok("f01: hatch invoke returned (session.log) before H1: JMX compactionDiskSpaceCheck(false) rc 0",
           "compactionDiskSpaceCheck(false) -> null" in read(os.path.join(HERE, "cluster", "f01", "session.log")))
        ok("f01: no automatic compaction ran: exactly one ks1 `Compacting` line in the whole system.log (H2's)",
           len(ev["compacting"]) == 1)

    elif label == "inflight":
        t2, slow = ds["t2"], ds["slow"]
        R0 = sum(slow)
        U1 = int(tr["I1"]["U_before"])
        B1 = java_round((U1 - FLOOR) * pct)
        ok("inflight: pct was planned as B = R0 + 3.2 s: B(I1) = %d, R0 + 3.2 s = %d (s = %d)"
           % (B1, R0 + 3.2 * (R0 / 8.0), R0 / 8.0), abs(B1 - (R0 + 3.2 * R0 / 8.0)) < 2 * MIB)
        ok("inflight: three bursts of check lines in the raw debug.log: I1 (t), the slow task, I2 (t2)", len(gs) == 3,
           "%d bursts: %s" % (len(gs), [len(g) for g in gs]))
        g1, gslow, g2 = gs
        sim1, d1, a1 = ladder(t_lens, B1)
        ok("inflight I1: one pass, requested = total of t = %d <= available %d (n = 0, 9a)" % (total, g1[0]["avail"]),
           len(g1) == 1 and g1[0]["req"] == total and abs(g1[0]["avail"] - B1) <= 1 and g1[0]["req"] <= g1[0]["avail"])
        ok("inflight slow task: its own pass requested = R0 = %d (the sum of its Data.db lengths) <= available: "
           "admitted whole while nothing else ran" % R0,
           len(gslow) == 1 and gslow[0]["req"] == R0 and gslow[0]["req"] <= gslow[0]["avail"])
        # I2: t2's passes
        R = g2[0]["req"] - sum(t2)
        sim2, d2, a2 = ladder(t2, g2[0]["avail"], extra=R)
        ok("inflight I2: first pass requested %d = total of t2 %d + R %d" % (g2[0]["req"], sum(t2), R), R > 0)
        ok("inflight I2: the raw `requested` equal R + the t2 ladder simulated from its Data.db lengths: %s" % sim2,
           [l["req"] for l in g2] == sim2)
        ok("inflight I2: %d passes, %d inputs dropped (9a: 5), last pass the first with requested <= available"
           % (len(g2), len(g2) - 1),
           len(g2) - 1 == PRED["inflight"]["I2"] and not a2 and g2[-1]["req"] <= g2[-1]["avail"]
           and all(l["req"] > l["avail"] for l in g2[:-1]))
        ok("inflight I2: all `available` within 1 MiB of the first (the store's free space falls as `slow` writes)",
           all(abs(l["avail"] - g2[0]["avail"]) <= MIB for l in g2),
           "range %d .. %d" % (min(l["avail"] for l in g2), max(l["avail"] for l in g2)))
        ok("inflight alone vs in flight: t alone dropped 0; t2 with `slow` running dropped %d" % d2, d1 == 0 and d2 == 5)
        # B at the I2 trigger, and R, from the sampler interpolated to the raw line's time
        ss = samples("inflight")
        ts_ = [float(r["epoch"]) for r in ss]
        ser_avail = [(t_, int(r["avail"])) for t_, r in zip(ts_, ss)]
        t_line = g2[0]["ts"]
        Ut = interp(ser_avail, t_line)
        Bt = java_round((Ut - FLOOR) * pct)
        ok("inflight I2: `available` of the first t2 pass %d = round((U(t) - 50 MiB) x pct), U(t) = %.0f from the "
           "sampler's df at the line's time: %d, within 1 MiB" % (g2[0]["avail"], Ut, Bt),
           abs(Bt - g2[0]["avail"]) <= MIB, "difference %d B" % (Bt - g2[0]["avail"]))
        ser_slow = []
        for t_, r in zip(ts_, ss):
            tk = json.loads(r["tasks"])
            if "slow" in tk:
                prog, tot, totc, kind = tk["slow"]
                ser_slow.append((t_, totc * (1.0 - prog / float(tot))))
        Rs = interp(ser_slow, t_line)
        ok("inflight I2: R from the line (%d) vs the slow task's remaining write read from sstable_tasks and "
           "interpolated to the line's time (%.0f): %.0f B apart (%.3f%%), within 16 MiB"
           % (R, Rs or -1, abs(R - Rs) if Rs else -1, 100 * abs(R - Rs) / R if Rs else -1),
           Rs is not None and abs(R - Rs) <= 16 * MIB)
        ok("inflight I2: the slow task was running (a `major compaction` row for `slow`) at the line's time, and "
           "its pass was logged before the t2 check", Rs is not None and gslow[-1]["ts"] < g2[0]["ts"])
        red = in_window(ev["reducing"], g2)
        ok("inflight I2: system.log `Reducing scope` x5, `has only` x5, no abort", len(red) == 5
           and len(in_window(ev["hasonly"], g2)) == 5 and not in_window(ev["abortwarn"], g2) and not ev["errors"])
        ok("inflight: ks1 `Compacting` lines: t (8 inputs), slow (8), t2 (3 inputs) — three in all",
           sorted(c[1] for c in ev["compacting"]) == [3, 8, 8], str([c[1] for c in ev["compacting"]]))
        t2c = [d for d in ev["compacted"] if d[1] == 3]
        kept2 = sum(sorted(t2)[:3])
        ok("inflight I2: `Compacted … 3 sstables`, output %.0f B ~ the kept inputs %d (within 0.01%%); output <= "
           "available - R = %d" % (t2c[0][3] if t2c else -1, kept2, g2[-1]["avail"] - R),
           bool(t2c) and abs(t2c[0][3] - kept2) <= 0.0001 * kept2 + 2048 and t2c[0][3] <= g2[-1]["avail"] - R)
        i2 = tr["I2"]
        ok("inflight I2: files of t2 8 -> 6 (1 output + 5 shed); rc 0; counters +1/+5/+0 (script's JMX read) = log "
           "events 5", i2["files_before"] == "8" and i2["files_after"] == "6" and i2["rc"] == "0"
           and (i2["reduced_delta"], i2["dropped_delta"], i2["aborted_delta"]) == ("1", "5", "0") and len(red) == 5)
        i1 = tr["I1"]
        ok("inflight I1: rc 0, files 8 -> 1, counters +0/+0/+0, no warning in its window",
           i1["rc"] == "0" and i1["files_after"] == "1"
           and (i1["reduced_delta"], i1["dropped_delta"], i1["aborted_delta"]) == ("0", "0", "0")
           and not in_window(ev["reducing"], g1))
        ok("inflight: no 'Compaction space check is disabled' line", not ev["disabled"])
        du_t2 = [int(r["du_t2"]) for r in ss]
        ok("inflight I2: sampler du of ks1.t2 rose by %d B = %.4f x the kept inputs %d"
           % (max(du_t2) - du_t2[0], (max(du_t2) - du_t2[0]) / float(kept2), kept2),
           0.95 <= (max(du_t2) - du_t2[0]) / float(kept2) <= 1.05)


def main():
    unit_tier()
    for label in ("d95", "f15", "f08", "f04", "f01", "inflight"):
        check_label(label)
    # harness schema (the table options cannot be read back from the logs)
    cr = read(os.path.join(HERE, "..", "..", "..", "harness",
                           "max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-"
                           "availableForCompaction", "cluster-run.py"))
    print("\n== HARNESS (the schema the run script executed)")
    ok("tables: STCS with 'enabled': 'false', pk int PRIMARY KEY, v blob, default compression",
       "SizeTieredCompactionStrategy', 'enabled': 'false'" in cr and "pk int PRIMARY KEY, v blob" in cr
       and "compression" not in re.search(r'CREATE TABLE[^\n]*', cr).group(0))
    print("\n%s" % ("ALL CHECKS HOLD" if not FAILS else "FAILED: %d — %s" % (len(FAILS), FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
