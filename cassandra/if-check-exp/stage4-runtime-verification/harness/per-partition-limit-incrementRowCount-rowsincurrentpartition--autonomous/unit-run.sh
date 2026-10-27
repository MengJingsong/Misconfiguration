#!/bin/bash
# Unit tier driver (B2) of per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous (tag q77, pc07, slot 7).
# Usage: bash unit-run.sh <tree> <outdir> [source rows] [reps]    defaults 20000 and 5; other values are shakedown only.
set -u
TREE=${1:?}; OUT=${2:?}; SRC=${3:-20000}; REPS=${4:-5}
HARN=$(cd "$(dirname "$0")" && pwd)
PKG=test/unit/org/apache/cassandra/db
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) source=$SRC reps=$REPS host=$(hostname -s)"
cp "$HARN"/PerPartitionLimitProbeTest.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw STAGE4_SRC=$SRC STAGE4_REPS=$REPS; rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.db.PerPartitionLimitProbeTest (STAGE4_OUT=$STAGE4_OUT)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.PerPartitionLimitProbeTest -Dtest.timeout=3600000 -Dtest.jvm.args=-XX:-UseTLAB -Dorg.jboss.byteman.contrib.bmunit.agent.port=19170 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
grep -q '^done=1' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "unit.txt has no done=1"
python3 -I "$HARN/analyze_unit.py" "$STAGE4_OUT/unit.txt" "$SRC" | tee "$OUT/summary.txt" | tee -a "$LOG"
grep -q '^EXPECTED first trigger.*: ok' "$OUT/summary.txt" || log "FIRST-TRIGGER CHECK FAILED (warm point L=100 w=16 did not stop at 100 rows)"
log "leftover java for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE[/ ]" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
