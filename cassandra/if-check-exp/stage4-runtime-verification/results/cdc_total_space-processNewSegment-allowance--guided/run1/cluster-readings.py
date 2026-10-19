#!/usr/bin/env python3
"""Reads the cluster tier's raw files and prints the tables of results §4.1; writes cluster-readings.json.

usage: cluster-readings.py <cluster directory holding one folder per value> <cdc-analyze.py>

Per value it reads settings.txt, phases.csv, readings.csv, sampler.csv, sampler.events, cdc-verdict.txt, system.log, the
stress outputs, release-probe.txt and the consumer files, and re-runs cdc-analyze.py on the trace and the timeline. Every number
comes from those files; nothing is typed in by hand.
"""
import csv
import gzip
import json
import os
import re
import statistics
import subprocess
import sys

ORDER = ["b144", "b272", "b528", "bdef", "s16", "n144", "n528", "c272"]


def num(s):
    s = s.strip().replace(",", "")
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def stress_totals(path):
    """(errors, partitions) from a cassandra-stress summary, or (None, None) if it did not finish."""
    if not os.path.exists(path):
        return None, None
    text = open(path).read()
    e = re.search(r"Total errors\s*:\s*([\d,]+)", text)
    p = re.search(r"Total partitions\s*:\s*([\d,]+)", text)
    return (num(e.group(1)) if e else None, num(p.group(1)) if p else None)


def read_log(d):
    """system.log, or the committed system.log.gz (only the WARN and ERROR lines and the CDCWriteException headers: the counts the checks use)."""
    p = os.path.join(d, "system.log")
    if os.path.exists(p):
        return open(p).read().splitlines()
    return gzip.open(p + ".gz", "rt").read().splitlines()


def read_value(d, analyzer):
    r = {"label": os.path.basename(d)}
    st = open(os.path.join(d, "settings.txt")).read()
    g = lambda key: (re.search(key + r"\s*\|\s*(\S+)", st) or [None, None])[1]
    r["A_MiB"] = num(re.sub(r"\D", "", g("cdc_total_space") or ""))
    r["S_MiB"] = num(re.sub(r"\D", "", g("commitlog_segment_size") or ""))
    r["blocking"] = g("cdc_block_writes") == "True" or g("cdc_block_writes") == "true"
    S = r["S_MiB"] << 20
    A = r["A_MiB"] << 20
    r["k"] = A // S
    r["exact"] = A % S == 0
    # phases and readings
    phases = {}
    for line in open(os.path.join(d, "phases.csv")):
        if "," in line:
            ms, name = line.strip().split(",", 1)
            phases[name] = int(ms)
    rows = list(csv.DictReader(open(os.path.join(d, "readings.csv"))))
    by_phase = {x["phase"]: x for x in rows if x["phase"] in ("idle", "A", "Bend", "Rend", "Cend")}
    r["L_idle"] = num(by_phase["idle"]["links"]) if "idle" in by_phase else None
    r["L_A"] = num(by_phase["A"]["links"]) if "A" in by_phase else None
    end = by_phase.get("Bend") or by_phase.get("Cend")
    r["Failures_end"] = end["Failures"] if end else None
    r["L_after_release"] = num(by_phase["Rend"]["links"]) if "Rend" in by_phase else None
    # sampler csv: exact per-tick counts
    ticks = []
    for line in open(os.path.join(d, "sampler.csv")).read().splitlines()[1:]:
        f = line.split(",")
        ticks.append(dict(ms=int(f[0]), links=int(f[1]), bytes=int(f[2]), alloc=int(f[3]), idx=int(f[4]), idxb=int(f[5]), gap=int(f[7])))
    r["max_gap_ms"] = max(t["gap"] for t in ticks)
    r["peak_L"] = max(t["links"] for t in ticks)
    r["bytes_not_LxS"] = sum(1 for t in ticks if t["bytes"] != t["links"] * S)
    def win(a, b):
        return [t for t in ticks if phases[a] <= t["ms"] <= phases[b]]
    if "B_start" in phases and "B_end" in phases:
        w = win("B_start", "B_end")
        last = [t["links"] for t in ticks if phases["B_end"] - 20000 <= t["ms"] <= phases["B_end"]]
        r.update(B_peak=max(t["links"] for t in w), B_min=min(t["links"] for t in w), plateau=statistics.median(last),
                 plateau_bytes=max(t["bytes"] for t in ticks if phases["B_end"] - 20000 <= t["ms"] <= phases["B_end"]),
                 plateau_alloc=max(t["alloc"] for t in ticks if phases["B_end"] - 20000 <= t["ms"] <= phases["B_end"]))
    if "C_start" in phases and "C_end" in phases:
        w = win("C_start", "C_end")
        r.update(C_peak=max(t["links"] for t in w), C_min=min(t["links"] for t in w))
    # the first rejection traced: L at that moment
    trace = os.path.join(d, "cdc-verdict.txt")
    rej = [int(re.search(r"ms=(\d+)", l).group(1)) for l in open(trace) if l.startswith("reject ")]
    r["rejects_traced"] = len(rej)
    last_n = [int(re.search(r" n=(\d+)", l).group(1)) for l in open(trace) if l.startswith("reject ")]
    r["rejections_counted"] = last_n[-1] if last_n else 0
    if rej:
        before = [t for t in ticks if t["ms"] <= rej[0]]
        r["L_first_rejection"] = before[-1]["links"] if before else None
    # logs
    sl = read_log(d)
    warns = [l for l in sl if l.startswith("WARN") and "Rejecting mutation to keyspace" in l]
    ns = [int(m.group(1)) for l in warns for m in [re.search(r"Total CDC bytes on disk is (\d+)", l)] if m]
    r.update(warn_entries=len(warns), N_values=sorted(set(ns)),
             logged_rejected_writes=sum(1 for l in sl if l.startswith("org.apache.cassandra.exceptions.CDCWriteException")),
             error_entries=sum(1 for l in sl if l.startswith("ERROR")))
    # stress
    r["cdcB_errors"], r["cdcB_partitions"] = stress_totals(os.path.join(d, "stress-cdc-B.txt"))
    r["plainB_errors"], r["plainB_partitions"] = stress_totals(os.path.join(d, "stress-plain-B.txt"))
    r["cdcC_errors"], r["cdcC_partitions"] = stress_totals(os.path.join(d, "stress-cdc-C.txt"))
    # release
    rp = os.path.join(d, "release-probe.txt")
    if os.path.exists(rp):
        lines = open(rp).read().splitlines()
        r["release_attempts"] = len(lines)
        r["release_accepted"] = bool(lines) and re.search(r"rc=0", lines[-1]) is not None and not re.search(r"(?i)error|failure|exception", lines[-1])
        if "R_start" in phases and lines:
            r["release_ms"] = int(lines[-1].split(",")[0]) - phases["R_start"]
        cp = os.path.join(d, "consumer-release.txt")
        r["consumer_deleted"] = sum(1 for l in open(cp) if ",deleted," in l) if os.path.exists(cp) else None
    cp = os.path.join(d, "consumer.txt")
    if os.path.exists(cp):
        r["consumer_loop_deleted"] = sum(1 for l in open(cp) if ",deleted," in l)
    # the settle step (pass 2): probes, wait, slowest probe, last streak
    sp = os.path.join(d, "settle-probe.txt")
    if os.path.exists(sp):
        lines = [l for l in open(sp).read().splitlines() if l]
        took = [int(re.search(r"took_ms=(\d+)", l).group(1)) for l in lines]
        streaks = [int(re.search(r"streak=(\d+)", l).group(1)) if "streak=" in l else None for l in lines]
        r["settle_probes"] = len(lines)
        r["settle_wait_ms"] = int(lines[-1].split(",")[0]) - int(lines[0].split(",")[0]) + took[0] if lines else None
        r["settle_slowest_ms"] = max(took) if took else None
        r["settle_streak"] = streaks[-1]
    # the analysis (re-run with the final script)
    out = subprocess.run([sys.executable, analyzer, "--trace", trace, "--events", os.path.join(d, "sampler.events"), "--format", "sampler",
                          "--csv", os.path.join(d, "sampler.csv"), "--phases", os.path.join(d, "phases.csv"), "--json", os.path.join(d, "analysis.json")],
                         capture_output=True, text=True)
    open(os.path.join(d, "analysis.txt"), "w").write(out.stdout + out.stderr)
    try:
        a = json.load(open(os.path.join(d, "analysis.json")))
        r.update(creations=a.get("creations"), created_forbidden=a.get("creations_forbidden"), formula_violations=len(a.get("formula_violations", [])),
                 stale=a.get("stale_creations"), unambiguous=a.get("unambiguous_creations"), beyond_k=a.get("links_beyond_k"),
                 beyond_unexplained=len(a.get("links_beyond_k_unexplained_by_stale_counter", [])), deleteOld=a.get("deleteOld_calls"),
                 removed=a.get("links_removed"), removed_ascending=a.get("removed_in_ascending_order"))
    except Exception as e:  # noqa
        r["analysis_error"] = str(e)
    return r


def main():
    root, analyzer = sys.argv[1], sys.argv[2]
    rows = [read_value(os.path.join(root, l), analyzer) for l in ORDER if os.path.isdir(os.path.join(root, l))]
    json.dump(rows, open(os.path.join(root, "cluster-readings.json"), "w"), indent=1, default=str)
    blk = [r for r in rows if r["label"].startswith(("b", "s")) and r["blocking"]]
    print("| value | A MiB (read back) | S MiB | k | idle L | L at first rejection | plateau L (median last 20 s of B) | B peak / min L | link bytes at plateau (apparent / allocated) | N in the WARN lines | WARN entries / logged rejected writes / traced `reject n` | `Failures` at B end |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in blk:
        S = r["S_MiB"] << 20
        print("| %s | %s%s | %d | %d%s | %s | %s | %s | %s / %s | %s MiB / %s MiB | %s | %s / %s / %s | %s |" % (
            r["label"], r["A_MiB"], " (default)" if r["label"] == "bdef" else "", r["S_MiB"], r["k"], " (exact multiple)" if r["exact"] else "",
            r["L_idle"], r.get("L_first_rejection"), r.get("plateau"), r.get("B_peak"), r.get("B_min"),
            r.get("plateau_bytes", 0) // (1 << 20), r.get("plateau_alloc", 0) // (1 << 20),
            ("%d..%d (%d distinct)" % (r["N_values"][0], r["N_values"][-1], len(r["N_values"]))) if r["N_values"] else "-",
            r["warn_entries"], r["logged_rejected_writes"], r["rejections_counted"], r["Failures_end"]))
    print()
    print("| value | peak L over the run | ticks with bytes ≠ L×S | max sampler gap (ms) | segments created / forbidden | verdict formula violations | stale creations / unambiguous | links made beyond k | …not explained by a stale counter |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s | %s / %s | %s | %s / %s | %s | %s |" % (r["label"], r["peak_L"], r["bytes_not_LxS"], r["max_gap_ms"], r.get("creations"), r.get("created_forbidden"),
                                                                      r.get("formula_violations"), r.get("stale"), r.get("unambiguous"), r.get("beyond_k", "n/a"), r.get("beyond_unexplained", "n/a")))
    print()
    print("| value | non-CDC control B: errors / rows | CDC stress B: errors / rows attempted | release: consumer deleted | release: attempts, ms to the accepted write | L after release |")
    print("|---|---|---|---|---|---|")
    for r in blk:
        print("| %s | %s / %s | %s / %s | %s | %s, %s | %s |" % (r["label"], r["plainB_errors"], r["plainB_partitions"], r["cdcB_errors"], r["cdcB_partitions"], r.get("consumer_deleted"),
                                                          r.get("release_attempts"), ("%s (accepted)" % r.get("release_ms")) if r.get("release_accepted") else "NOT accepted", r["L_after_release"]))
    print()
    print("| value | settle: probes | wait (ms) | slowest probe (ms) | final streak of prompt probes |")
    print("|---|---|---|---|---|")
    for r in rows:
        if "settle_probes" in r:
            print("| %s | %s | %s | %s | %s |" % (r["label"], r["settle_probes"], r["settle_wait_ms"], r["settle_slowest_ms"], r["settle_streak"] if r["settle_streak"] is not None else "(single probe)"))
    nb = [r for r in rows if not r["blocking"]]
    if nb:
        print()
        print("| non-blocking value | A MiB | k | peak L (per-tick, whole run) | B min L | segments created | links removed | removed in ascending order | deleteOld calls | WARN entries | CDC stress B errors / rows | L at B's end |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in nb:
            print("| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s | %s / %s | %s |" % (r["label"], r["A_MiB"], r["k"], r["peak_L"], r.get("B_min"), r.get("creations"), r.get("removed"), r.get("removed_ascending"),
                                                                                  r.get("deleteOld"), r["warn_entries"], r["cdcB_errors"], r["cdcB_partitions"], r["L_after_release"] or r.get("B_min")))
    cc = [r for r in rows if r["label"] == "c272"]
    for r in cc:
        print()
        print("consumer control c272: WARN entries %s, logged rejected writes %s, peak L %s (k = %s), C window peak/min %s/%s, links deleted by the consumer loop %s, CDC stress errors / rows %s / %s, segments created %s" % (
            r["warn_entries"], r["logged_rejected_writes"], r["peak_L"], r["k"], r.get("C_peak"), r.get("C_min"), r.get("consumer_loop_deleted"), r["cdcC_errors"], r["cdcC_partitions"], r.get("creations")))


if __name__ == "__main__":
    main()
