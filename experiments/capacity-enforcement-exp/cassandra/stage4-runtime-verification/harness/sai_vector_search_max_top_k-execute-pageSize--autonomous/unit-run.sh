#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of sai_vector_search_max_top_k-execute-pageSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh
#   Runs TopKProbe100Test, TopKProbeDefaultTest, TopKProbe1500Test, each in its own `ant testsome` JVM.
# Env: C (clone, default $W/cassandra-run34), L (log dir), CLASSES (subset, for a shakedown).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run34}
L=${L:-$W/logs/sai_vector_search_max_top_k-execute-pageSize--autonomous/unit}
CLASSES=${CLASSES:-"100:TopKProbe100Test 1000:TopKProbeDefaultTest 1500:TopKProbe1500Test"}
PKG=org.apache.cassandra.index.sai.cql; D=$C/test/unit/org/apache/cassandra/index/sai/cql
mkdir -p "$L"; rm -f "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
pgrep -f 'cassandra.service.Cassandra''Daemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
for f in TopKProbeBase TopKProbe100Test TopKProbeDefaultTest TopKProbe1500Test; do
  cp "$H/$f.java" "$D/$f.java"; log "copied $f.java (sha256 $(shasum -a 256 "$D/$f.java" | cut -c1-16))"
done
for spec in $CLASSES; do
  V=${spec%%:*}; CLS=$PKG.${spec#*:}
  rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS   (V=$V)"
  ( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS ) > "$L/ant-$V.log" 2>&1
  rc=$?
  tl=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
  [ -n "$tl" ] && cp "$tl" "$L/TEST-$V.log"
  cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST-$V.xml" 2>/dev/null
  grep -o 'PROBE .*' "$L/TEST-$V.log" 2>/dev/null > "$L/probe-$V.txt"
  log "V=$V ant rc=$rc; $(grep -m1 -E 'Tests run' "$L/ant-$V.log" || echo 'no Tests run line'); PROBE lines=$(wc -l < "$L/probe-$V.txt" | tr -d ' ')"
  { echo "V=$V ant rc=$rc"; grep -m1 -E 'Tests run' "$L/ant-$V.log"; cat "$L/probe-$V.txt"; } >> "$L/summary.txt"
done
for f in TopKProbeBase TopKProbe100Test TopKProbeDefaultTest TopKProbe1500Test; do rm -f "$D/$f.java"; done
rm -rf "$C/build/test/classes/org/apache/cassandra/index/sai/cql/TopKProbe"*.class
log "probes removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run done"
