#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U5 of 2026-10-27) of cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label> [jvmargs]
#   r1:    unit-run.sh r1                       (frozen values: rfp.n=20000, rfp.ts=1000,10000,32000,100000, rfp.ctl=100000)
#   shake: unit-run.sh shake "-Drfp.n=2000 -Drfp.ts=100,1000,10000 -Drfp.ctl=10000"
# Copies RfpCapProbeTest.java into clone C (default $W/cassandra-run50), runs ant test-jvm-dtest-some once, copies the
# TEST log/XML, extracts the RFPU lines, removes the copied test. Logs: $W/logs/cached_rows_fail_threshold-queryProtectedPartitions-i/unit-<label>/
# (structure adapted from harness/paxos_cache_size-close-active--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1; JA=${2:-}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run50}
CLS=org.apache.cassandra.distributed.test.RfpCapProbeTest
L=$W/logs/cached_rows_fail_threshold-queryProtectedPartitions-i/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) test_sha=$(shasum -a 256 "$H/RfpCapProbeTest.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16) jvmargs=[$JA]"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/distributed/org/apache/cassandra/distributed/test/RfpCapProbeTest.java
cp "$H/RfpCapProbeTest.java" "$T"
rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS*.xml "$C"/build/test/cassandra
log "+ ant -Dlocal.repository=\$W/m2 test-jvm-dtest-some -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
s0=$(date +%s)
if [ -n "$JA" ]; then
  ( cd "$C" && ant -Dlocal.repository=$W/m2 test-jvm-dtest-some -Dtest.name=$CLS -Dtest.jvm.args="$JA" ) > "$L/ant.log" 2>&1
else
  ( cd "$C" && ant -Dlocal.repository=$W/m2 test-jvm-dtest-some -Dtest.name=$CLS ) > "$L/ant.log" 2>&1
fi
rc=$?
log "ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line')"
cp "$C"/build/test/output/TEST-$CLS*.xml "$L/" 2>/dev/null || log "no JUnit XML"
TL=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" 2>/dev/null | head -1)
if [ -n "$TL" ]; then cp "$TL" "$L/TEST-$CLS.log"; else log "no TEST log; using ant.log"; TL="$L/ant.log"; fi
grep -h 'RFPU' "$L/TEST-$CLS.log" "$L/ant.log" 2>/dev/null | sed 's/^.*\(RFPU[-A-Z]*,\)/\1/; s/^.*\(RFPU-END\)$/\1/' | awk '!seen[$0]++' > "$L/rfpu.txt"
log "RFPU lines: $(grep -c '^RFPU,' "$L/rfpu.txt"); KA: $(grep -c '^RFPU-KA' "$L/rfpu.txt"); END: $(grep -c '^RFPU-END' "$L/rfpu.txt")"
grep '^RFPU,' "$L/rfpu.txt" | while read -r l; do log "  $l"; done
rm -f "$T"; rm -rf "$C/build/test/classes/org/apache/cassandra/distributed/test/RfpCapProbeTest"*.class
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
pgrep -f 'RfpCapProbeTest' >/dev/null && log "WARNING: a test JVM is still running" || log "no test JVM left"
log "unit-run $LABEL done"
