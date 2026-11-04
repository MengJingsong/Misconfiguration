#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh
#   run 1: no variables (N = 5000).  shakedown: MNC_N=500 L=<dir> unit-run.sh
# Copies MaxNodeConnectionsCapTest.java into the clone, runs one `ant testsome` JVM, keeps the logs, removes the test.
# Env: C (clone, default $W/cassandra-run39), L (log dir).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run39}
L=${L:-$W/logs/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/unit}
CLS=org.apache.cassandra.index.sai.disk.v1.MaxNodeConnectionsCapTest
D=$C/test/unit/org/apache/cassandra/index/sai/disk/v1
mkdir -p "$L"; rm -f "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') MNC_N=${MNC_N:-unset(5000)}"
pgrep -f 'cassandra.service.Cassandra''Daemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
cp "$H/MaxNodeConnectionsCapTest.java" "$D/"; log "copied MaxNodeConnectionsCapTest.java (sha256 $(shasum -a 256 "$D/MaxNodeConnectionsCapTest.java" | cut -c1-16))"
rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS"
T0=$(date +%s)
( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS ) > "$L/ant.log" 2>&1
rc=$?
tl=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
[ -n "$tl" ] && cp "$tl" "$L/TEST.log"
cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST.xml" 2>/dev/null
grep -o 'PROBE .*' "$L/TEST.log" 2>/dev/null > "$L/probe.txt"
log "ant rc=$rc seconds=$(( $(date +%s) - T0 )); $(grep -m1 -E 'Tests run' "$L/ant.log" || echo 'no Tests run line'); PROBE lines=$(wc -l < "$L/probe.txt" | tr -d ' ')"
{ echo "ant rc=$rc"; grep -m1 -E 'Tests run' "$L/ant.log"; cat "$L/probe.txt"; } > "$L/summary.txt"
rm -f "$D/MaxNodeConnectionsCapTest.java"
rm -f "$C/build/test/classes/org/apache/cassandra/index/sai/disk/v1/MaxNodeConnectionsCapTest"*.class
log "test removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries; leftover tmp graph files: $(find "$C/build" /tmp "${TMPDIR:-/tmp}" -maxdepth 3 -name 'mnc-graph-*' 2>/dev/null | wc -l | tr -d ' ')"
log "unit-run done"
