#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of page_size_fail_threshold-execute-pageSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [jvm-args]
#   run 1: no argument (2000 rows; thresholds (5,10), (500,1000), (-1,-1); entry points D and L; cases c1..c6)
#   shakedown only: unit-run.sh "-Dprobe.rows=50 -Dprobe.thr=5:10"
# Env: C (clone, default $W/cassandra-run33), L (log dir).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run33}
L=${L:-$W/logs/page_size_fail_threshold-execute-pageSize--autonomous/unit}
JA=${1:-}
mkdir -p "$L"; rm -f "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) jvm-args=[$JA]"
pgrep -f 'cassandra.service.Cassandra''Daemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
CLS=org.apache.cassandra.db.guardrails.PageSizeBranchProbeTest
T=$C/test/unit/org/apache/cassandra/db/guardrails/PageSizeBranchProbeTest.java
cp "$H/PageSizeBranchProbeTest.java" "$T"; log "probe copied to $T (sha256 $(shasum -a 256 "$T" | cut -c1-16))"
rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
if [ -n "$JA" ]; then
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
  ( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS -Dtest.jvm.args="$JA" ) > "$L/ant.log" 2>&1
else
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS"
  ( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS ) > "$L/ant.log" 2>&1
fi
rc=$?
tl=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
[ -n "$tl" ] && cp "$tl" "$L/TEST.log"
cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST.xml" 2>/dev/null
grep -o 'PROBE .*' "$L/TEST.log" 2>/dev/null > "$L/probe.txt"
grep '^ERROR' "$L/TEST.log" 2>/dev/null | grep 'page_size violated' > "$L/error-pagesize-lines.txt"
grep '^WARN' "$L/TEST.log" 2>/dev/null | grep 'page_size violated' > "$L/warn-pagesize-lines.txt"
log "ant rc=$rc; $(grep -m1 -E 'Tests run' "$L/ant.log" || echo 'no Tests run line'); PROBE lines=$(wc -l < "$L/probe.txt" | tr -d ' '); ERROR page_size lines=$(wc -l < "$L/error-pagesize-lines.txt" | tr -d ' '); WARN page_size lines=$(wc -l < "$L/warn-pagesize-lines.txt" | tr -d ' ')"
{ echo "ant rc=$rc"; grep -m1 -E 'Tests run' "$L/ant.log"; echo "error_pagesize_lines=$(wc -l < "$L/error-pagesize-lines.txt" | tr -d ' ')"; echo "warn_pagesize_lines=$(wc -l < "$L/warn-pagesize-lines.txt" | tr -d ' ')"; cat "$L/probe.txt"; } > "$L/summary.txt"
rm -f "$T"
rm -rf "$C/build/test/classes/org/apache/cassandra/db/guardrails/PageSizeBranchProbeTest"*.class
log "probe removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run done"
