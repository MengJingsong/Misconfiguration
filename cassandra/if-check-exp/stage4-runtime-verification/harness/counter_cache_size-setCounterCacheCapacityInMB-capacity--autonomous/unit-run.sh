#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-27) of counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label> [N]
#   label: shake (N default 20000) or r1 (N = 200000 as frozen). Copies CounterCacheCapacityProbeTest.java into the clone,
#   runs ant testsome once (both @Test methods in one JVM), copies the JUnit XML and the test log, removes the copied file.
# Clone C (default $W/cassandra-run46). Logs: $W/logs/counter_cache_size-setCounterCacheCapacityInMB/unit-<label>/
set -uo pipefail
LABEL=$1; N=${2:-}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run46}
L=$W/logs/counter_cache_size-setCounterCacheCapacityInMB/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) harness_sha=$(shasum -a 256 "$H/CounterCacheCapacityProbeTest.java" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/service/CounterCacheCapacityProbeTest.java
cp "$H/CounterCacheCapacityProbeTest.java" "$T"
rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-org.apache.cassandra.service.CounterCacheCapacityProbeTest.xml
JA=""; [ -n "$N" ] && JA="-Dccr.n=$N"
log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=org.apache.cassandra.service.CounterCacheCapacityProbeTest ${JA:+-Dtest.jvm.args=$JA}"
s0=$(date +%s)
if [ -n "$JA" ]; then
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.CounterCacheCapacityProbeTest -Dtest.jvm.args="$JA" ) > "$L/ant.log" 2>&1
else
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.CounterCacheCapacityProbeTest ) > "$L/ant.log" 2>&1
fi
rc=$?; log "ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line')"
cp "$C/build/test/output/TEST-org.apache.cassandra.service.CounterCacheCapacityProbeTest.xml" "$L/" 2>/dev/null || log "no JUnit XML"
TL=$(find "$C/build/test/logs" -name 'TEST-org.apache.cassandra.service.CounterCacheCapacityProbeTest.log' | head -1)
[ -n "$TL" ] && cp "$TL" "$L/test.log" || log "no test log"
grep -h 'CCR ' "$L/test.log" 2>/dev/null | sed 's/^.*CCR /CCR /' > "$L/stdout.txt"
grep -v 'CCR sample' "$L/stdout.txt" > "$L/summary.txt"
rm -f "$T"; rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-org.apache.cassandra.service.CounterCacheCapacityProbeTest.xml"
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
log "unit-run $LABEL done"
