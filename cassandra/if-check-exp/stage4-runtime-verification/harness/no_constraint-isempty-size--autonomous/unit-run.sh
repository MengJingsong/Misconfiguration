#!/usr/bin/env bash
# Unit tier driver for no_constraint-isempty-size--autonomous. Usage: unit-run.sh <tree> <outdir> <mode: check|alloc|count>
#   check: instrument checks + rule parse only    alloc: ResultSetBuilder.build() allocation per call    count: ResultSet.isEmpty() return values
# <tree> is a copy-source.sh copy built with `ant build-test` (never cassandra/cassandra-5.0.9/ and never a tree a node runs from).
set -u
TREE=${1:?}; OUT=${2:?}; MODE=${3:?}
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"; LOG=$OUT/session-$MODE.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run mode=$MODE tree=$TREE jdk=$(java -version 2>&1 | head -1) host=$(hostname -s)"
( cd "$H" && md5sum ResultSetIsEmptyTest.java Alloc.java rules-alloc.btm rules-count.btm unit-run.sh analyze.py selfcheck.py 2>/dev/null ) > "$OUT/harness.md5"
cp "$H/ResultSetIsEmptyTest.java" "$TREE/test/unit/org/apache/cassandra/cql3/" || exit 1
cd "$TREE" || exit 1
rm -rf "$OUT/alloc-classes" && mkdir -p "$OUT/alloc-classes" && javac -d "$OUT/alloc-classes" "$H/Alloc.java" && jar cf "$OUT/stage4-alloc.jar" -C "$OUT/alloc-classes" . || exit 3
CP="build/test/classes:build/classes/main:build/classes/thrift:build/lib/jars/*:build/test/lib/jars/*:lib/*:$OUT/stage4-alloc.jar"
BM=$TREE/build/lib/jars/byteman-4.0.20.jar
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes test/unit/org/apache/cassandra/cql3/ResultSetIsEmptyTest.java >> "$LOG" 2>&1 || exit 2
grep -E "^--(add|illegal)" conf/jvm11-server.options > "$OUT/jvm11-opens.args"
rm -rf "$OUT/raw-$MODE" "$OUT/storage-$MODE"; mkdir -p "$OUT/raw-$MODE"
RULES=rules-alloc.btm; [ "$MODE" = count ] && RULES=rules-count.btm
TRACE=$OUT/raw-$MODE/trace.txt
JOPT="@$OUT/jvm11-opens.args -Xmx2g -Xbootclasspath/a:$OUT/stage4-alloc.jar -javaagent:$TREE/build/lib/jars/jamm-0.4.0.jar -Dstage4.out=$OUT/raw-$MODE -Dstage4.byteman.out=$TRACE -Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=$OUT/storage-$MODE -Dlogback.configurationFile=file://$TREE/test/conf/logback-test.xml -Dcassandra.skip_sync=true -Dcassandra.ring_delay_ms=1000 -Dcassandra.tolerate_sstable_size=true"
if [ "$MODE" = check ]; then
  JOPT="$JOPT -Dstage4.checkonly=1"
  for r in rules-alloc.btm rules-count.btm; do
    java -cp "$BM:build/lib/jars/*:build/classes/main:lib/*:$OUT/stage4-alloc.jar" org.jboss.byteman.check.TestScript "$H/$r" > "$OUT/testscript-$r.log" 2>&1
    log "TestScript $r: $(grep -c '^Type checked rule' "$OUT/testscript-$r.log") rules type checked; $(grep '^TestScript:' "$OUT/testscript-$r.log")"
  done
else
  JOPT="$JOPT -javaagent:$BM=script:$H/$RULES"
fi
log "+ java $JOPT org.junit.runner.JUnitCore org.apache.cassandra.cql3.ResultSetIsEmptyTest"
java $JOPT -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.cql3.ResultSetIsEmptyTest > "$OUT/junit-$MODE.log" 2>&1
rc=$?
log "java exit $rc"; grep -E "STAGE4|^OK|^FAIL|Tests run" "$OUT/junit-$MODE.log" | tee -a "$LOG"
exit $rc
