#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of hints_buffer_size-allocateBytes-prev--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [extra jvm args]
#   run 1:     unit-run.sh                      (B in {1 MiB, 32 MiB, 64 MiB}, pool case at 32 MiB)
#   shakedown: unit-run.sh "-Dhbcap.sizes=262144 -Dhbcap.pool=false"
# Always passes -XX:MaxDirectMemorySize=1g (B2a). Env: C (clone, default $W/cassandra-run36), L (log dir).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run36}
L=${L:-$W/logs/hints_buffer_size-allocateBytes-prev--autonomous/unit}
JA="-XX:MaxDirectMemorySize=1g ${1:-}"
mkdir -p "$L"; rm -f "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') jvm-args=[$JA]"
pgrep -f 'cassandra.service.Cassandra''Daemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
CLS=org.apache.cassandra.hints.HintsBufferCapTest
T=$C/test/unit/org/apache/cassandra/hints/HintsBufferCapTest.java
cp "$H/HintsBufferCapTest.java" "$T"; log "test copied to $T (sha256 $(shasum -a 256 "$T" | cut -c1-16))"
rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS -Dtest.jvm.args="$JA" ) > "$L/ant.log" 2>&1
rc=$?
tl=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
[ -n "$tl" ] && cp "$tl" "$L/TEST.log"
cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST.xml" 2>/dev/null
grep -o 'HBCAP .*' "$L/TEST.log" 2>/dev/null > "$L/hbcap.txt"
log "ant rc=$rc; $(grep -m1 -E 'Tests run' "$L/ant.log" || echo 'no Tests run line'); HBCAP lines=$(wc -l < "$L/hbcap.txt" | tr -d ' ')"
{ echo "ant rc=$rc"; grep -E 'Tests run|BUILD' "$L/ant.log"; cat "$L/hbcap.txt"; } > "$L/summary.txt"
rm -f "$T"
rm -rf "$C/build/test/classes/org/apache/cassandra/hints/HintsBufferCapTest"*.class
log "test removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run done"
