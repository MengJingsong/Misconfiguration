#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir>
# Sweep JVM (-Xmx1g) and control JVM (-Xmx6g), java + JUnitCore, no Byteman. Not ant testsome.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE jdk=$(java -version 2>&1 | head -1)"
D=$TREE/test/unit/org/apache/cassandra/db/tries; mkdir -p $D
cp "$HARN"/InMemoryTrieAllocBlockTest.java $D/ || exit 1
( cd $HARN && md5sum * ) > "$OUT/harness.md5"
cd $TREE
CP="build/classes/main:build/test/classes:test/conf:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar 2>/dev/null | tr '\n' ':')"
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes $D/InMemoryTrieAllocBlockTest.java >> "$LOG" 2>&1 || exit 2
rc_all=0
runjvm() {  # name, heap, extra opts
  local name=$1 heap=$2; shift 2
  local d=$OUT/$name; rm -rf "$d"; mkdir -p "$d"
  log "+ java -Xmx$heap $* (out=$d)"
  java -Xmx$heap -Dstage4.out=$d "$@" -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.db.tries.InMemoryTrieAllocBlockTest > "$d/junit.log" 2>&1
  local rc=$?; log "java exit $rc ($name)"; tail -n 3 "$d/junit.log" | tee -a "$LOG"; [ $rc -ne 0 ] && rc_all=$rc
  cat "$d/raw.csv" >> "$OUT/raw-all.csv"
}
rm -f "$OUT/raw-all.csv"
runjvm sweep 1g -Dstage4.mode=sweep
runjvm control 6g -Dstage4.mode=control
log "unit-run done rc=$rc_all"
exit $rc_all
