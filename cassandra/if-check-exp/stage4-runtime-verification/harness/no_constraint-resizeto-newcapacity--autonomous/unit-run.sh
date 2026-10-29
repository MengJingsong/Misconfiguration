#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir>
# Compiles the test into <tree> (a copy-source.sh tree), then runs one fresh JVM per C and two control JVMs
# (java -Xmx512m + JUnitCore + the Byteman agent). Not ant testsome.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE jdk=$(java -version 2>&1 | head -1)"
D=$TREE/test/unit/org/apache/cassandra/io/util; mkdir -p $D
cp "$HARN"/SafeMemoryResizeToTest.java "$HARN"/NativeLedger.java $D/ || exit 1
( cd $HARN && md5sum * ) > "$OUT/harness.md5"
cd $TREE
CP="build/classes/main:build/test/classes:test/conf:$(ls build/lib/jars/*.jar build/test/lib/jars/*.jar 2>/dev/null | tr '\n' ':')"
log "+ javac"; javac -nowarn -cp "$CP" -d build/test/classes $D/NativeLedger.java $D/SafeMemoryResizeToTest.java >> "$LOG" 2>&1 || exit 2
BMJAR=$TREE/build/lib/jars/byteman-4.0.20.jar
rc_all=0
runjvm() {  # name, extra java opts
  local name=$1; shift
  local d=$OUT/$name; rm -rf "$d"; mkdir -p "$d"
  log "+ java -Xmx512m $* (out=$d)"
  java -Xmx512m -Dstage4.out=$d "$@" -javaagent:$BMJAR=script:$HARN/rules.btm -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.io.util.SafeMemoryResizeToTest > "$d/junit.log" 2>&1
  local rc=$?; log "java exit $rc ($name)"; tail -n 3 "$d/junit.log" | tee -a "$LOG"; [ $rc -ne 0 ] && rc_all=$rc
  cat "$d/raw.csv" >> "$OUT/raw-all.csv"
}
rm -f "$OUT/raw-all.csv"
for C in 1024 65536 1048576 67108864 536870912; do
  runjvm "c$C" -Dstage4.mode=sweep -Dstage4.c=$C
done
runjvm control-default -Dstage4.mode=control
runjvm control-dob1 -Dstage4.mode=control -Dcassandra.DOB_DOUBLING_THRESHOLD_MB=1
log "unit-run done rc=$rc_all"
exit $rc_all
