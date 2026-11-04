#!/bin/bash
# Unit tier driver (B2) of rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous.
# Usage: bash unit-run.sh <tree> <outdir> [rows]     rows defaults to 1000; other values are shakedown only.
# Copies the test into the tree (never the shared repo tree), runs it with ant testsome, then analyze_unit.py.
set -u
TREE=${1:?}; OUT=${2:?}; ROWS=${3:-1000}
HARN=$(cd "$(dirname "$0")" && pwd)
PKG=test/unit/org/apache/cassandra/db
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) rows=$ROWS host=$(hostname -s)"
cp "$HARN"/RowsPerPartitionTest.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw STAGE4_ROWS=$ROWS; rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.db.RowsPerPartitionTest (STAGE4_OUT=$STAGE4_OUT rows=$ROWS)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.RowsPerPartitionTest -Dtest.timeout=3600000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
grep -q '^firsttrigger=OK' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "FIRST-TRIGGER CHECK FAILED: N=10 left no cache entry (or the test did not run)"
grep -q '^done=1' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "unit.txt has no done=1"
python3 -I "$HARN/analyze_unit.py" "$STAGE4_OUT/unit.txt" | tee "$OUT/summary.txt" | tee -a "$LOG"
log "leftover java for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
