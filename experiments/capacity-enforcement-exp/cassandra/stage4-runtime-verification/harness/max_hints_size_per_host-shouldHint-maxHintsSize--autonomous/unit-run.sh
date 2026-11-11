#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-27) of max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label> [n] [cs]
#   label: shake (e.g. n=600 cs=0,1) or r1 (defaults n=20000, cs=0,1,4,16 as frozen).
#   Copies HintsSizeCapUnitTest.java into the clone, runs ant testsome once, copies the JUnit XML and the test log,
#   removes the copied file. Clone C (default $W/cassandra-run48).
#   Logs: $W/logs/max_hints_size_per_host-shouldHint/unit-<label>/
# (structure adapted from harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1; N=${2:-}; CS=${3:-}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run48}
CLS=org.apache.cassandra.hints.HintsSizeCapUnitTest
L=$W/logs/max_hints_size_per_host-shouldHint/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) test_sha=$(shasum -a 256 "$H/HintsSizeCapUnitTest.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/hints/HintsSizeCapUnitTest.java
cp "$H/HintsSizeCapUnitTest.java" "$T"
rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS.xml "$C"/build/test/cassandra
JA=""; [ -n "$N" ] && JA="$JA -Dhsc.n=$N"; [ -n "$CS" ] && JA="$JA -Dhsc.cs=$CS"
log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
s0=$(date +%s)
if [ -n "$JA" ]; then
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args="$JA" ) > "$L/ant.log" 2>&1
else
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS ) > "$L/ant.log" 2>&1
fi
rc=$?; log "ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line')"
cp "$C/build/test/output/TEST-$CLS.xml" "$L/" 2>/dev/null || log "no JUnit XML"
TL=$(find "$C/build/test/logs" -name "TEST-$CLS.log" | head -1)
[ -n "$TL" ] && cp "$TL" "$L/test.log" || log "no test log"
grep -h 'HSC ' "$L/test.log" 2>/dev/null | sed 's/^.*HSC /HSC /' > "$L/stdout.txt"
grep -v 'HSC ROW ' "$L/stdout.txt" > "$L/summary.txt"
rm -f "$T"; rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
rm -rf "$C/build/test/classes/org/apache/cassandra/hints/HintsSizeCapUnitTest"*.class
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
log "unit-run $LABEL done"
