#!/bin/bash
# Unit tier driver (B2) of cql-row-limit-hasEnoughLiveData-rowLimit--autonomous.
# Usage: bash unit-run.sh <tree> <outdir> [rows]     rows defaults to 1000; other values are shakedown only.
set -u
TREE=${1:?}; OUT=${2:?}; ROWS=${3:-1000}
HARN=$(cd "$(dirname "$0")" && pwd)
PKG=test/unit/org/apache/cassandra/db
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) rows=$ROWS host=$(hostname -s)"
cp "$HARN"/HasEnoughLiveDataProbeTest.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw STAGE4_ROWS=$ROWS; rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.db.HasEnoughLiveDataProbeTest (STAGE4_OUT=$STAGE4_OUT rows=$ROWS)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.HasEnoughLiveDataProbeTest -Dtest.timeout=3600000 -Dorg.jboss.byteman.contrib.bmunit.agent.port=19140 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
grep -q '^firsttrigger=OK' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "FIRST-TRIGGER CHECK FAILED: R=100 left no 100-row entry / direct call for L=100 not true (or the test did not run)"
grep -q '^done=1' "$STAGE4_OUT/unit.txt" 2>/dev/null || log "unit.txt has no done=1"
python3 -I "$HARN/analyze_unit.py" "$STAGE4_OUT/unit.txt" | tee "$OUT/summary.txt" | tee -a "$LOG"
log "leftover java for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE[/ ]" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
