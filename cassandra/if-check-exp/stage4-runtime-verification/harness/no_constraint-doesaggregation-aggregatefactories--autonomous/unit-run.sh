#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [byteman=0|1] [sizes]
# <tree> is a copy-source.sh tree that has been through `ant build-test` (never cassandra/cassandra-5.0.9/). Compiles the test into
# <tree>, runs it with plain java + JUnitCore (not ant testsome: its fork JVM options are fixed). byteman=1 attaches rules.btm
# (counts only); jamm is attached in both modes (used by the doesaggregation case only).
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; BM=${4:-0}; SIZES=${5:-1000,10000,100000}
CLS=NoneDoesAggregationAllocTest
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE byteman=$BM sizes=$SIZES jdk=$(java -version 2>&1 | head -1) host=$(hostname)"
mkdir -p $TREE/test/unit/org/apache/cassandra/cql3
cp "$HARN"/$CLS.java $TREE/test/unit/org/apache/cassandra/cql3/ || exit 1
( cd $HARN && md5sum * ) > "$OUT/harness.md5"
cd $TREE
CP="build/classes/main:build/test/classes:test/conf:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar 2>/dev/null | tr '\n' ':')"
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes test/unit/org/apache/cassandra/cql3/$CLS.java >> "$LOG" 2>&1 || exit 2
MODS="-Djdk.attach.allowAttachSelf=true --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
rm -rf "$OUT/raw"; mkdir -p "$OUT/raw"
JOPT="-Xmx2g $MODS -Dstage4.out=$OUT/raw -Dstage4.sizes=$SIZES -Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage -Dlogback.configurationFile=file://$TREE/test/conf/logback-test.xml -javaagent:$TREE/build/lib/jars/jamm-0.4.0.jar"
if [ "$BM" = 1 ]; then
  BMJAR=$TREE/build/lib/jars/byteman-4.0.20.jar
  rm -f $OUT/raw/trace.txt
  JOPT="$JOPT -Dstage4.trace=$OUT/raw/trace.txt -javaagent:$BMJAR=script:$HARN/rules.btm"
fi
log "+ java $JOPT org.junit.runner.JUnitCore org.apache.cassandra.cql3.$CLS"
java $JOPT -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.cql3.$CLS > "$OUT/junit.log" 2>&1
rc=$?
log "java exit $rc"; grep -a "^OK\|Tests run\|^FAIL\|AssertionError\|Exception in" "$OUT/junit.log" | head -5 | tee -a "$LOG"
exit $rc
