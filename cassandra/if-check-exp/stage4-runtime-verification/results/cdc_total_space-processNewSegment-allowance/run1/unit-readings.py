#!/usr/bin/env python3
"""Reads the unit tier's raw files and prints one table of readings (results §4.1) and writes unit-readings.json.

usage: unit-readings.py <unit directory holding one folder per JVM> <cdc-analyze.py>

Per JVM folder it reads readings.txt (the harness test's STAGE4 lines), cdc-verdict.txt (the creation trace) and
junit.xml, and runs cdc-analyze.py on the pair. Nothing is typed in by hand: every number comes from those files.
"""
import json
import os
import re
import subprocess
import sys

ORDER = ["u16", "u48", "u80", "u128", "u144", "u272", "u280-s16", "u80-nb", "u144-nb"]


def kv(line):
    return dict(re.findall(r"(\w+)=(\S+)", line))


def read_jvm(d, analyzer):
    r = {"label": os.path.basename(d)}
    rd = os.path.join(d, "readings.txt")
    if not os.path.exists(rd):
        r["error"] = "no readings.txt"
        return r
    lines = open(rd).read().splitlines()
    for line in lines:
        body = re.sub(r"^ms=\d+ ", "", line)
        if body.startswith("config "):
            c = kv(body)
            r.update(mode=c["mode"], A_MiB=int(c["totalSpaceMiB"]), S_MiB=int(c["segmentMiB"]), k=int(c["k"]), exact=c["exactMultiple"] == "true")
        elif body.startswith("idle "):
            r["idle_links"] = int(kv(body)["links"])
        elif body.startswith("firstRejection "):
            f = kv(body)
            r.update(accepted=int(f["accepted"]), L_first=int(f["links"]), linkBytes=int(f["linkBytes"]), counter=int(f["counter"]), idxBytes=int(f["idxBytes"]))
        elif body.startswith("rejectionCounter "):
            r["N"] = int(kv(body)["N"])
        elif body.startswith("afterTenMore "):
            f = kv(body)
            r.update(rejected_after=int(f["rejected"]), L_after=int(f["links"]))
        elif body.startswith("nonCdcWrite "):
            r["nonCdc_accepted"] = kv(body)["accepted"] == "true"
        elif body.startswith("release resumed="):
            f = kv(body)
            r.update(resumed=f["resumed"] == "true", resume_ms=int(f["afterMs"]), rejected_before=int(f["rejectedBefore"]), L_released=int(f["links"]))
        elif body.startswith("release skipped"):
            r["resumed"] = "skipped"
        elif body.startswith("nonBlocking rowsWritten"):
            f = kv(body)
            r.update(rows=int(f["rowsWritten"]), distinct=int(f["distinctLinksSeen"]), maxLinks=int(f["maxLinks"]), finalLinks=int(f["finalLinks"]), deleted=int(f["deletedLinks"]))
        elif body.startswith("nonBlocking bytesWritten"):
            f = kv(body)
            r.update(bytesWritten=int(f["bytesWritten"]), bytesRetained=int(f["bytesRetained"]))
        elif body.startswith("RESULT "):
            m = re.search(r"mismatches=(\d+)", body)
            r["mismatches"] = int(m.group(1))
            r["mismatch_list"] = body[body.find("["):] if "[" in body else ""
    r["checks_pass"] = sum(1 for l in lines if " check PASS " in l)
    r["checks_mismatch"] = sum(1 for l in lines if " check MISMATCH " in l)
    j = os.path.join(d, "junit.xml")
    if os.path.exists(j):
        head = open(j).read()[:3000]
        g = lambda a: (re.search(a + r'="(\d+)"', head) or [None, "?"])[1]
        r["junit"] = "tests=%s failures=%s errors=%s" % (g("tests"), g("failures"), g("errors"))
    tr = os.path.join(d, "cdc-verdict.txt")
    if os.path.exists(tr):
        r["trace_creations"] = len(re.findall(r"^pre ", open(tr).read(), re.M))
        out = subprocess.run([sys.executable, analyzer, "--trace", tr, "--events", rd, "--format", "unit", "--json", os.path.join(d, "analysis.json")],
                             capture_output=True, text=True)
        open(os.path.join(d, "analysis.txt"), "w").write(out.stdout + out.stderr)
        try:
            a = json.load(open(os.path.join(d, "analysis.json")))
            r.update(formula_violations=len(a.get("formula_violations", [])), stale=a.get("stale_creations"), unambiguous=a.get("unambiguous_creations"),
                     beyond_k=a.get("links_beyond_k"), beyond_unexplained=len(a.get("links_beyond_k_unexplained_by_stale_counter", [])),
                     peak=a.get("peak_links"))
        except Exception as e:  # noqa
            r["analysis_error"] = str(e)
    return r


def main():
    root, analyzer = sys.argv[1], sys.argv[2]
    labels = [l for l in ORDER if os.path.isdir(os.path.join(root, l))]
    rows = [read_jvm(os.path.join(root, l), analyzer) for l in labels]
    json.dump(rows, open(os.path.join(root, "unit-readings.json"), "w"), indent=1)

    print("| JVM | mode | A MiB | S MiB | k | idle L | accepted | L at first rejection | N (message) | N − L×S | after 10 more: L | non-CDC | release (ms, rejected first) | checks (pass / mismatch) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("mode") == "nonblocking":
            continue
        S = r["S_MiB"] << 20
        print("| %s | %s | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s | %s | %d / %d |" % (
            r["label"], r["mode"], r["A_MiB"], r["S_MiB"], r["k"], r.get("idle_links", "-"), r.get("accepted", "-"), r.get("L_first", "-"),
            r.get("N", "-"), (r["N"] - r["L_first"] * S) if "N" in r and "L_first" in r else "-", r.get("L_after", "-"),
            "accepted" if r.get("nonCdc_accepted") else "-",
            ("%s, %s" % (r["resume_ms"], r["rejected_before"])) if isinstance(r.get("resumed"), bool) and r["resumed"] else r.get("resumed", "-"),
            r["checks_pass"], r["checks_mismatch"]))
    print()
    print("| JVM | trace: creations | verdict formula violations | stale creations (unambiguous) | links made beyond k | …of which not explained by a stale counter | peak L (per-tick) |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s / %s | %s | %s | %s |" % (r["label"], r.get("trace_creations", "-"), r.get("formula_violations", "-"), r.get("stale", "-"), r.get("unambiguous", "-"),
                                                      r.get("beyond_k", "n/a (non-blocking)" if r.get("mode") == "nonblocking" else "-"), r.get("beyond_unexplained", "-"), r.get("peak", "-")))
    print()
    print("| JVM (non-blocking) | rows | distinct links made | max L | final L | links deleted | bytes written | bytes retained | checks (pass / mismatch) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if r.get("mode") == "nonblocking":
            print("| %s | %s | %s | %s | %s | %s | %s | %s | %d / %d |" % (r["label"], r.get("rows"), r.get("distinct"), r.get("maxLinks"), r.get("finalLinks"), r.get("deleted"),
                                                                    r.get("bytesWritten"), r.get("bytesRetained"), r["checks_pass"], r["checks_mismatch"]))
    print()
    for r in rows:
        if r.get("mismatches"):
            print("mismatches in %s: %s" % (r["label"], r.get("mismatch_list", "")))
    print("junit: " + "; ".join("%s %s" % (r["label"], r.get("junit", "?")) for r in rows))


if __name__ == "__main__":
    main()
