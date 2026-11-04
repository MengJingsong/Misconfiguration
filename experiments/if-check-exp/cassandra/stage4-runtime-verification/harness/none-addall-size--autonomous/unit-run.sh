#!/usr/bin/env bash
# Unit tier driver for none-addall-size--autonomous. Usage: unit-run.sh <tree> <outdir> <mode: plain|bm|check>
#   plain: allocation / retained-size readings, no agent      bm: Byteman branch trace (allocation columns not used)
#   check: instrument checks only (known-answer, empty window, rules parse) - no sweep
# <tree> is a copy-source.sh copy that has been built with `ant build-test` (never a tree a node runs from and never cassandra/cassandra-5.0.9/).
set -u
TREE=${1:?}; OUT=${2:?}; MODE=${3:?}
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"; LOG=$OUT/session-$MODE.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run mode=$MODE tree=$TREE jdk=$(java -version 2>&1 | head -1) host=$(hostname -s)"
( cd "$H" && md5sum AddAllBranchTest.java rules.btm unit-run.sh analyze.py selfcheck.py 2>/dev/null ) > "$OUT/harness.md5"
cp "$H/AddAllBranchTest.java" "$TREE/test/unit/org/apache/cassandra/db/" || exit 1
cd "$TREE" || exit 1
CP="build/test/classes:build/classes/main:build/classes/thrift:build/lib/jars/*:build/test/lib/jars/*:lib/*"
BM=$TREE/build/lib/jars/byteman-4.0.20.jar
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes test/unit/org/apache/cassandra/db/AddAllBranchTest.java >> "$LOG" 2>&1 || exit 2
grep -E "^--(add|illegal)" conf/jvm11-server.options > "$OUT/jvm11-opens.args"
rm -rf "$OUT/raw-$MODE"; mkdir -p "$OUT/raw-$MODE"
JOPT="@$OUT/jvm11-opens.args -Xmx2g -javaagent:$TREE/build/lib/jars/jamm-0.4.0.jar -Dstage4.out=$OUT/raw-$MODE -Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage-$MODE -Dlogback.configurationFile=file://$TREE/test/conf/logback-test.xml"
case $MODE in
  check) JOPT="$JOPT -Dstage4.checkonly=1"
         java -cp "$BM:build/lib/jars/*:build/classes/main:lib/*" org.jboss.byteman.check.TestScript "$H/rules.btm" > "$OUT/testscript.log" 2>&1
         log "TestScript: $(grep -c '^Type checked rule' "$OUT/testscript.log") rules type checked; $(grep '^TestScript:' "$OUT/testscript.log")" ;;
  bm)    JOPT="$JOPT -Dstage4.trace=$OUT/raw-bm/trace.txt -javaagent:$BM=script:$H/rules.btm" ;;
esac
log "+ java $JOPT org.junit.runner.JUnitCore org.apache.cassandra.db.AddAllBranchTest"
java $JOPT -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.db.AddAllBranchTest > "$OUT/junit-$MODE.log" 2>&1
rc=$?
log "java exit $rc"; grep -E "STAGE4|^OK|^FAIL|Tests run" "$OUT/junit-$MODE.log" | tee -a "$LOG"
exit $rc
