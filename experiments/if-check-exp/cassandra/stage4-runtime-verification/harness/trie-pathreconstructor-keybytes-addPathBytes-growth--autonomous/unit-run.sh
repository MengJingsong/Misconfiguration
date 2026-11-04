#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir>
# Copies the test into <tree> (a copy-source.sh tree; never a tree a node is running from), then runs ant testsome once in a fresh JVM.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD)"
cp "$HARN"/PathBufferSizeTest.java $TREE/test/unit/org/apache/cassandra/db/tries/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh *.btm ) | tee -a "$LOG" > "$OUT/harness.md5"
ulimit -n 100000
export STAGE4_OUT=$OUT
log "+ ant testsome -Dtest.name=org.apache.cassandra.db.tries.PathBufferSizeTest"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.tries.PathBufferSizeTest -Dtest.timeout=3600000 < /dev/null ) > "$OUT/ant.log" 2>&1
r=$?; log "ant exit $r"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
exit $r
