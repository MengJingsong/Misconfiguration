#!/usr/bin/env bash
# drains.sh <logs dir>: monitor counts from debug.log* (plain and rolled .zip), grep -o only (never whole lines).
# One output line per drain message: "<n> operations were slow|timed out in the last <ms> msecs" followed by its
# per-name counts; then totals.
L=$1
{ for f in $(ls -tr $L/debug.log*.zip 2>/dev/null) $L/debug.log; do
    [ -e "$f" ] || continue
    case "$f" in *.zip) unzip -p "$f" ;; *) cat "$f" ;; esac
  done; } | python3 -I $(dirname "$0")/squash.py | grep -aoE '^[A-Z]+ +\[[A-Za-z0-9:_ -]+\] [0-9T:,-]+ MonitoringTask.java|[0-9]+ operations (were slow|timed out) in the last [0-9]+ msecs|was slow [0-9]+ times|timed out [0-9]+ times|\.\.\. \([0-9]+ were dropped\)|ALLOW FILTERING>, (total )?time [0-9]+ msec' \
  | python3 -I -c '
import sys, re
dr = []
for l in sys.stdin:
    l = l.strip()
    if "MonitoringTask.java" in l:
        dr.append({"ts": l.split()[-2], "hdr": "", "slow": [], "single": 0, "dropped": 0}); continue
    if not dr: continue
    d = dr[-1]
    m = re.match(r"(\d+) operations (were slow|timed out) in the last (\d+) msecs", l)
    if m: d["hdr"] = l; d["n"] = int(m.group(1)); d["kind"] = m.group(2); d["ms"] = int(m.group(3)); continue
    m = re.match(r"(was slow|timed out) (\d+) times", l)
    if m: d["slow"].append(int(m.group(2))); continue
    if l.startswith("ALLOW FILTERING>"): d["single"] += 1; continue
    m = re.match(r"\.\.\. \((\d+) were dropped\)", l)
    if m: d["dropped"] = int(m.group(1))
dr = [d for d in dr if d["hdr"]]
for d in dr:
    names = len(d["slow"]) + d["single"]
    print("%s %-10s n=%d interval_ms=%d names=%d queued=%d dropped=%d multi=%s" % (d["ts"], d["kind"].replace(" ", "_"), d["n"], d["ms"], names,
          sum(d["slow"]) + d["single"], d["dropped"], ",".join(map(str, d["slow"]))))
s = [d for d in dr if d["kind"] == "were slow"]; f = [d for d in dr if d["kind"] != "were slow"]
print("TOTAL slow drains %d (queue full=queued>=50: %d; dropped>0: %d; max names %d; max queued %d); failed drains %d (max queued %d)" % (
    len(s), sum(1 for d in s if sum(d["slow"]) + d["single"] >= 50), sum(1 for d in s if d["dropped"] > 0),
    max([len(d["slow"]) + d["single"] for d in s] or [0]), max([sum(d["slow"]) + d["single"] for d in s] or [0]),
    len(f), max([sum(d["slow"]) + d["single"] for d in f] or [0])))
'
