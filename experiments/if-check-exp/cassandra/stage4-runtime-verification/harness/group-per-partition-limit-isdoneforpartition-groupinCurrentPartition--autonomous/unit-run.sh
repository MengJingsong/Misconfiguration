#!/bin/bash
# Unit tier driver (B2) of group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous.
# Usage: bash unit-run.sh <tree> <outdir> [rows]   rows defaults to 100000; other values are shakedown only.
set -u
TREE=${1:?}; OUT=${2:?}; ROWS=${3:-100000}
HARN=$(cd "$(dirname "$0")" && pwd)
PKG=test/unit/org/apache/cassandra/db
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) rows=$ROWS host=$(hostname -s)"
cp "$HARN"/GroupPerPartitionLimitTest.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) > "$OUT/harness.md5"; cat "$OUT/harness.md5" >> "$LOG"
export STAGE4_OUT=$OUT/raw STAGE4_ROWS=$ROWS; rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.db.GroupPerPartitionLimitTest (STAGE4_OUT=$STAGE4_OUT rows=$ROWS)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.GroupPerPartitionLimitTest -Dtest.timeout=3600000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
grep -q '^firsttrigger=OK' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "FIRST-TRIGGER CHECK FAILED: N=10 did not return 10 groups with few rows pulled (or the test did not run)"
grep -q '^done=1' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "unit.txt has no done=1"
python3 -I "$HARN/analyze_unit.py" "$STAGE4_OUT/unit.txt" | tee "$OUT/summary.txt" | tee -a "$LOG"
log "leftover java for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
