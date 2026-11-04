#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U4 of 2026-10-27) of
# native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label>
#   r1:    unit-run.sh r1                                   (frozen values -1,0,3,5; 8 channels, 6 from 10.0.0.1 and 2 from 10.0.0.2)
#   shake: EXTRA="-Dntpip.values=-1,2" unit-run.sh shake    (not a reading)
# Copies PerIpLimitProbeTest.java into clone C (default $W/cassandra-run56), runs one ant testsome JVM, copies the TEST log,
# extracts the START/READBACK/CH/PROBE/CLOSED/END lines, removes the copied test.
# (adapted from harness/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1
STEM=native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run56}; EXTRA=${EXTRA:-}
CLS=org.apache.cassandra.transport.PerIpLimitProbeTest
L=$W/logs/$STEM/unit-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL extra=[$EXTRA] clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) test_sha=$(shasum -a 256 "$H/PerIpLimitProbeTest.java" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
T=$C/test/unit/org/apache/cassandra/transport/PerIpLimitProbeTest.java
cp "$H/PerIpLimitProbeTest.java" "$T"
rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS*.xml
if [ -n "$EXTRA" ]; then
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$EXTRA\""
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS "-Dtest.jvm.args=$EXTRA" ) > "$L/ant.log" 2>&1
else
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS"
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS ) > "$L/ant.log" 2>&1
fi
rc=$?
log "ant rc=$rc; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line'); $(grep -m1 'BUILD' "$L/ant.log")"
cp "$C"/build/test/output/TEST-$CLS*.xml "$L/TEST.xml" 2>/dev/null || log "no JUnit XML"
TL=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" 2>/dev/null | head -1)
if [ -n "$TL" ]; then cp "$TL" "$L/TEST.log"; else log "no TEST log; using ant log"; cp "$L/ant.log" "$L/TEST.log"; fi
grep -h -o -E '(START|READBACK|CH|PROBE|CLOSED|END),.*$|END$' "$L/TEST.log" > "$L/probe.txt"
log "lines: READBACK $(grep -c '^READBACK,' "$L/probe.txt") CH $(grep -c '^CH,' "$L/probe.txt") PROBE $(grep -c '^PROBE,' "$L/probe.txt") CLOSED $(grep -c '^CLOSED,' "$L/probe.txt") END $(grep -c '^END' "$L/probe.txt")"
grep '^PROBE,\|^CLOSED,\|^READBACK,' "$L/probe.txt" | while read -r l; do log "  $l"; done
grep -q '^END' "$L/probe.txt" || log "STOP CONDITION: no END line (tier invalid)"
grep -A3 'FAILED\|Exception' "$L/ant.log" | head -10 | while read -r l; do log "  ant: $l"; done
rm -f "$T"; rm -rf "$C/build/test/classes/org/apache/cassandra/transport/PerIpLimitProbeTest"*.class
log "copied test removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
pgrep -f 'PerIpLimitProbeTest' >/dev/null && log "WARNING: a test JVM is still running" || log "no test JVM left"
log "unit-run $LABEL done"
