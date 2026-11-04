#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [sets]
# tree: a copy-source.sh tree never used by a node. sets: space list of main|cap|cap38 (default all three).
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; SETS=${4:-"main cap cap38"}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) sets=$SETS"
cp "$HARN"/CompressedInputStreamOversizeTest.java $TREE/test/unit/org/apache/cassandra/streaming/compression/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh *.md ) > "$OUT/harness.md5"; cat "$OUT/harness.md5" >> "$LOG"
ulimit -n 100000
export STAGE4_OUT=$OUT/raw; mkdir -p "$STAGE4_OUT"
declare -A LIM=( [main]=512m [cap]=16m [cap38]=38m )
rc_all=0
for s in $SETS; do
  export STAGE4_SET=$s
  log "+ ant testsome -Dtest.name=org.apache.cassandra.streaming.compression.CompressedInputStreamOversizeTest -Dtest.jvm.args=-XX:MaxDirectMemorySize=${LIM[$s]}   (STAGE4_SET=$s)"
  ( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.streaming.compression.CompressedInputStreamOversizeTest -Dtest.jvm.args="-XX:MaxDirectMemorySize=${LIM[$s]}" -Dtest.timeout=1800000 < /dev/null ) > "$OUT/ant-$s.log" 2>&1
  rc=$?; log "ant exit $rc (set $s)"; tail -n 6 "$OUT/ant-$s.log" | tee -a "$LOG"
  [ $rc -ne 0 ] && rc_all=$rc
done
exit $rc_all
