#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U4 of 2026-10-27) of native_transport_max_concurrent_connections-channelActive-limit--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; [JVMARGS="-Dprobe.n=16 -Dprobe.s=1024"] unit-run.sh <label>
# Copies ConnectionLimitProbeTest.java into clone C (default $W/cassandra-run53), runs ant testsome once, copies the TEST
# log/XML, extracts the PROBE lines, removes the copied test. Logs: $W/logs/native_transport_max_concurrent_connections-channelActive-limit/unit-<label>/
# (structure adapted from harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run53}; JVMARGS=${JVMARGS:-}
CLS=org.apache.cassandra.transport.ConnectionLimitProbeTest
L=$W/logs/native_transport_max_concurrent_connections-channelActive-limit/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) jvmargs=[$JVMARGS] test_sha=$(shasum -a 256 "$H/ConnectionLimitProbeTest.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/transport/ConnectionLimitProbeTest.java
cp "$H/ConnectionLimitProbeTest.java" "$T"
rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS*.xml
log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$JVMARGS\""
s0=$(date +%s)
( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS "-Dtest.jvm.args=$JVMARGS" ) > "$L/ant.log" 2>&1
rc=$?
log "ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line'); $(grep -m1 'BUILD' "$L/ant.log")"
cp "$C"/build/test/output/TEST-$CLS*.xml "$L/" 2>/dev/null || log "no JUnit XML"
TL=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" 2>/dev/null | head -1)
if [ -n "$TL" ]; then cp "$TL" "$L/TEST-$CLS.log"; else log "no TEST log; using ant.log"; cp "$L/ant.log" "$L/TEST-$CLS.log"; fi
grep -h 'PROBE ' "$L/TEST-$CLS.log" | sed 's/^.*\(PROBE .*\)$/\1/' | awk '!seen[$0]++' > "$L/probe.txt"
log "PROBE lines: $(wc -l < "$L/probe.txt" | tr -d ' ')"
while read -r l; do log "  $l"; done < "$L/probe.txt"
grep -A3 'FAILED\|AssertionError' "$L/ant.log" | head -10 | while read -r l; do log "  ant: $l"; done
rm -f "$T"; rm -rf "$C/build/test/classes/org/apache/cassandra/transport/ConnectionLimitProbeTest"*.class
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
pgrep -f 'ConnectionLimitProbeTest' >/dev/null && log "WARNING: a test JVM is still running" || log "no test JVM left"
log "unit-run $LABEL done rc=$rc"
