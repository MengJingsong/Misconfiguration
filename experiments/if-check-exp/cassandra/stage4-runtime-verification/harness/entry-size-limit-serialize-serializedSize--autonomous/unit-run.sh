#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [arms] [scale]
# Copies the probe into <tree> (a copy-source.sh tree, never a tree a node runs from), runs ant testsome in the background-safe way, logs everything.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; ARMS=${4:-}; SCALE=${5:-1}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) arms=${ARMS:-all} scale=$SCALE"
cp "$HARN"/SerializingCacheLimitTest.java $TREE/test/unit/org/apache/cassandra/cache/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw STAGE4_SCALE=$SCALE
[ -n "$ARMS" ] && export STAGE4_ARMS=$ARMS
rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
export MALLOC_ARENA_MAX=1 MALLOC_MMAP_THRESHOLD_=65536 MALLOC_TRIM_THRESHOLD_=0
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.cache.SerializingCacheLimitTest (env MALLOC_ARENA_MAX=1 MALLOC_MMAP_THRESHOLD_=65536 MALLOC_TRIM_THRESHOLD_=0)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.cache.SerializingCacheLimitTest -Dtest.timeout=3600000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
exit $rc
