#!/usr/bin/env bash
# Unit tier (B2, amendments U1-U5 of 2026-10-27) of max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh <label> [classes]
#   r1:    unit-run.sh r1                 (frozen: the four classes 1 4 16 Default)
#   shake: unit-run.sh shake "4"
# Copies RangeCapProbe<V>Test.java into clone C (default $W/cassandra-run51), runs ant testsome once per class, copies the TEST
# logs/XML, extracts the RNGU lines, removes the copied tests and their classes.
# Logs: $W/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/unit-<label>/
# (structure adapted from harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/unit-run.sh)
set -uo pipefail
LABEL=$1; CLASSES=${2:-"1 4 16 Default"}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run51}
PKG=org.apache.cassandra.service.reads.range
TD=$C/test/unit/org/apache/cassandra/service/reads/range
L=${W:?}/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/unit-$LABEL; mkdir -p "$L"; rm -rf "${L:?}"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run $LABEL classes=[$CLASSES] clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is running"; exit 1; }
: > "$L/rngu.txt"
for V in $CLASSES; do
  CLS=$PKG.RangeCapProbe${V}Test
  log "--- class $CLS test_sha=$(shasum -a 256 "$H/RangeCapProbe${V}Test.java" | cut -c1-16)"
  cp "$H/RangeCapProbe${V}Test.java" "$TD/"
  rm -rf "$C"/build/test/logs "$C"/build/test/output/TEST-$CLS*.xml
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS"
  s0=$(date +%s)
  ( cd "$C" && ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS ) > "$L/ant-$V.log" 2>&1
  rc=$?
  log "ant rc=$rc after $(( $(date +%s) - s0 )) s; $(grep -m1 'Tests run' "$L/ant-$V.log" || echo 'no Tests run line')"
  cp "$C"/build/test/output/TEST-$CLS*.xml "$L/" 2>/dev/null || log "no JUnit XML"
  TL=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" 2>/dev/null | head -1)
  if [ -n "$TL" ]; then cp "$TL" "$L/TEST-$CLS.log"; else log "no TEST log; using ant log"; fi
  n0=$(wc -l < "$L/rngu.txt")
  grep -h 'RNGU,' "$L/TEST-$CLS.log" "$L/ant-$V.log" 2>/dev/null | sed 's/^.*\(RNGU,\)/\1/' | awk '!seen[$0]++' >> "$L/rngu.txt"
  log "RNGU lines for $V: $(( $(wc -l < "$L/rngu.txt") - n0 ))"; tail -n +$((n0 + 1)) "$L/rngu.txt" | while read -r l; do log "  $l"; done
  rm -f "$TD/RangeCapProbe${V}Test.java"; rm -f "$C"/build/test/classes/org/apache/cassandra/service/reads/range/RangeCapProbe${V}Test*.class
done
log "copied tests removed; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
pgrep -f 'RangeCapProbe' >/dev/null && log "WARNING: a test JVM is still running" || log "no test JVM left"
log "unit-run $LABEL done"
