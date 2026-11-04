#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir>
# tree: a copy-source.sh tree never used by a node (built with ant build-test).
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) host=$(hostname)"
mkdir -p $TREE/test/unit/org/apache/cassandra/index/sasi/memory
cp "$HARN"/TrieMemIndexSizeTest.java $TREE/test/unit/org/apache/cassandra/index/sasi/memory/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh *.md ) > "$OUT/harness.md5" 2>/dev/null; cat "$OUT/harness.md5" >> "$LOG"
ulimit -n 100000
export STAGE4_OUT=$OUT/raw
mkdir -p "$STAGE4_OUT"
log "+ ant testsome -Dtest.name=org.apache.cassandra.index.sasi.memory.TrieMemIndexSizeTest"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.index.sasi.memory.TrieMemIndexSizeTest -Dtest.timeout=3000000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?; log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
exit $rc
