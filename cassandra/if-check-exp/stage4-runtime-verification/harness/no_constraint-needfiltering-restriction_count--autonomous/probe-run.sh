#!/bin/bash
# Usage: bash probe-run.sh <tree> <harness-dir> <outdir>; compiles NeedFilteringProbeTest into a copy-source.sh tree and runs it with plain java.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
mkdir -p $TREE/test/unit/org/apache/cassandra/cql3
cp "$HARN"/NeedFilteringProbeTest.java $TREE/test/unit/org/apache/cassandra/cql3/ || exit 1
cd $TREE
CP="build/classes/main:build/test/classes:test/conf:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar 2>/dev/null | tr '\n' ':')"
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes test/unit/org/apache/cassandra/cql3/NeedFilteringProbeTest.java >> "$LOG" 2>&1 || exit 2
JOPT="-Xmx1g -Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage -Dlogback.configurationFile=file://$TREE/test/conf/logback-test.xml -Djdk.attach.allowAttachSelf=true --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.rmi/sun.rmi.transport.tcp=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED"
log "+ java org.junit.runner.JUnitCore NeedFilteringProbeTest"
java $JOPT -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.cql3.NeedFilteringProbeTest > "$OUT/junit.log" 2>&1
rc=$?; log "java exit $rc"; grep -a "PROBE" "$OUT/junit.log" | sed "s/^.* - PROBE/PROBE/" | tee "$OUT/probe.txt"; tail -n 5 "$OUT/junit.log"
exit $rc
