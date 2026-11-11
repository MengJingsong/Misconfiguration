#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [byteman=0|1] [arms]
# Compiles the test into <tree> (a copy-source.sh tree, never a tree a node runs from), runs it with java -Xmx512m + JUnitCore (B2i.3); with byteman=1 attaches the rules (B2i.4).
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; BM=${4:-0}; ARMS=${5:-}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE byteman=$BM arms=${ARMS:-all} jdk=$(java -version 2>&1 | head -1)"
mkdir -p $TREE/test/unit/org/apache/cassandra/db/transform
cp "$HARN"/StackSpliceCapacityTest.java $TREE/test/unit/org/apache/cassandra/db/transform/ || exit 1
( cd $HARN && md5sum * ) > "$OUT/harness.md5"
cd $TREE
CP="build/classes/main:build/test/classes:test/conf:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar 2>/dev/null | tr '\n' ':')"
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes test/unit/org/apache/cassandra/db/transform/StackSpliceCapacityTest.java >> "$LOG" 2>&1 || exit 2
rm -rf "$OUT/raw"; mkdir -p "$OUT/raw"
JOPT="-Xmx512m -Dstage4.out=$OUT/raw -Dstage4.arms=${ARMS:-} -Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage -Dlogback.configurationFile=file://$TREE/test/conf/logback-test.xml"
if [ "$BM" = 1 ]; then
  BMJAR=$TREE/build/lib/jars/byteman-4.0.20.jar
  rm -f $OUT/raw/trace.txt
  JOPT="$JOPT -Dstage4.trace=$OUT/raw/trace.txt -javaagent:$BMJAR=script:$HARN/rules.btm"
fi
log "+ java $JOPT org.junit.runner.JUnitCore org.apache.cassandra.db.transform.StackSpliceCapacityTest"
eval java $JOPT -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.db.transform.StackSpliceCapacityTest > "$OUT/junit.log" 2>&1
rc=$?
log "java exit $rc"; tail -n 6 "$OUT/junit.log" | tee -a "$LOG"
exit $rc
