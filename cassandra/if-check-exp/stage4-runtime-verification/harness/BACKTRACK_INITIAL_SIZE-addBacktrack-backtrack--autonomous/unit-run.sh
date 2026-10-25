#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [thresholds, default "8 16 32"]
# Copies the test into <tree> (a copy-source.sh tree; never a tree a node runs from), then runs ant testsome once per threshold T (MiB) in a fresh JVM.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; TS=${4:-"8 16 32"}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) thresholds=$TS"
cp "$HARN"/BacktrackSizeTest.java $TREE/test/unit/org/apache/cassandra/db/tries/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh *.btm ) | tee -a "$LOG" > "$OUT/harness.md5"
ulimit -n 100000
rc=0
for T in $TS; do
  D=$OUT/T$T; rm -rf "$D"; mkdir -p "$D"
  export STAGE4_OUT=$D STAGE4_THRESHOLD_MIB=$T
  log "+ STAGE4_THRESHOLD_MIB=$T ant testsome -Dtest.name=org.apache.cassandra.db.tries.BacktrackSizeTest"
  ( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.tries.BacktrackSizeTest -Dtest.timeout=3600000 < /dev/null ) > "$D/ant.log" 2>&1
  r=$?; log "ant exit $r (T=$T)"; tail -n 6 "$D/ant.log" | tee -a "$LOG"
  [ $r -ne 0 ] && rc=$r
done
exit $rc
