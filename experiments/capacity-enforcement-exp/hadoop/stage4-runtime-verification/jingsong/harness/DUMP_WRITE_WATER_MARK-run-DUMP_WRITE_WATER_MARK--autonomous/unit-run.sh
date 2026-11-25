#!/usr/bin/env bash
# Unit tier (B2, amendment A1) for DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous. Runs ON the node.
# Every command and its output goes to $R/logs/unit-run.log. Usage: unit-run.sh [--compile-only]
set -uo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK--autonomous-run1
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
TDIR=$SRC/$MOD/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
OUT=$R/logs/unit
mkdir -p "$OUT"
exec > >(tee -a "$R/logs/unit-run.log") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
echo "=== unit tier ${1:-run} start $(date '+%F %T %Z') on $(hostname)"
run java -version; run mvn -v
cd "$SRC" || fail "no src"
run git describe --tags
[ -z "$(git status --short | grep -v TestDumpWaterMark.java)" ] || fail "source copy not clean"
sed -n 73p "$OFC" | grep -q 'private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;' || fail "line 73"
sed -n 379p "$OFC" | grep -q 'if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK) {' || fail "line 379"
run sed -n '73p;379p' "$OFC"
run cp "$R/harness/TestDumpWaterMark.java" "$TDIR/"
if [ "${1:-}" = --compile-only ]; then
  run mvn -B -o test-compile -pl "$MOD" -Dmaven.javadoc.skip=true > "$OUT/mvn-compile.log" 2>&1; rc=$?
  run grep -E 'BUILD|ERROR' "$OUT/mvn-compile.log" | tail -5; echo "compile rc=$rc"; exit $rc
fi
rm -rf "$SRC/$MOD/target/surefire-reports" "$R/unit-dump"
run mvn -B -o test -pl "$MOD" -Dtest=TestDumpWaterMark -Dmaven.javadoc.skip=true \
    "-Dmaven-surefire-plugin.argLine=-Xmx2048m -Ddumpwm.dir=$R/unit-dump" \
    > "$OUT/mvn-unit.log" 2>&1 || echo "mvn exit $? (surefire counts are read, not the exit code)"
run grep -E 'Tests run:|BUILD|ERROR' "$OUT/mvn-unit.log" | tail -10
mkdir -p "$OUT/surefire"
cp "$SRC/$MOD/target/surefire-reports/"*TestDumpWaterMark* "$OUT/surefire/" || fail "no surefire report"
grep -h '^DUMPWM' "$OUT/surefire/"*-output.txt > "$OUT/readings.txt" || grep -h 'DUMPWM M=' "$OUT/mvn-unit.log" > "$OUT/readings.txt"
run cat "$OUT/readings.txt"
run cat "$OUT/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt"
run ls -la "$R/unit-dump"
run jps
echo "=== unit tier end $(date '+%F %T %Z')"
