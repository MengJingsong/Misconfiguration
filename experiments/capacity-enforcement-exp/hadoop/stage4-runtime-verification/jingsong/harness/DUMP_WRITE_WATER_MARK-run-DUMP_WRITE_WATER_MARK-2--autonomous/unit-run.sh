#!/usr/bin/env bash
# Unit tier (B2 + amendment 2026-11-25) for DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous. Runs ON the node.
# Usage: unit-run.sh [--compile-only]. Every command and its output -> $R/logs/unit-run.log
set -uo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous-run1
SRC=$R/src; MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
TDIR=$SRC/$MOD/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
OUT=$R/logs/unit; mkdir -p "$OUT"
exec > >(tee -a "$R/logs/unit-run.log") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
echo "=== unit tier ${1:-run} start $(date '+%F %T %Z') on $(hostname)"
run java -version; run mvn -v | head -1
cd "$SRC" || fail "no src"
run git describe --tags
[ -z "$(git status --short -- "$MOD/src/main")" ] || fail "main source not clean"
sed -n 73p "$OFC" | grep -q 'private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;' || fail "line 73"
sed -n 379p "$OFC" | grep -q 'if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK) {' || fail "line 379"
sed -n 383p "$OFC" | grep -q 'if (nonSequentialWriteInMemory.get() < DUMP_WRITE_WATER_MARK) {' || fail "line 383"
run sed -n '73p;379p;383,386p' "$OFC"
run cp "$R/harness/TestDumpWaterMark.java" "$TDIR/"
mkdir -p "$SRC/$MOD/src/test/resources"
run cp "$R/harness/log4j.properties" "$SRC/$MOD/src/test/resources/log4j.properties"
run git status --short
if [ "${1:-}" = --compile-only ]; then
  run mvn -B -o test-compile -pl "$MOD" -Dmaven.javadoc.skip=true > "$OUT/mvn-compile.log" 2>&1; rc=$?
  grep -E 'BUILD|ERROR' "$OUT/mvn-compile.log" | tail -8; echo "compile rc=$rc"; exit $rc
fi
rm -rf "$SRC/$MOD/target/surefire-reports" "$R/unit-dump"; mkdir -p "$R/unit-dump"
run mvn -B -o test -pl "$MOD" -Dtest=TestDumpWaterMark -Dmaven.javadoc.skip=true \
    "-Dmaven-surefire-plugin.argLine=-Xmx1024m -Ddumpwm.dir=$R/unit-dump" > "$OUT/mvn-unit.log" 2>&1 \
    || echo "mvn exit $? (surefire counts are read, not the exit code)"
grep -E 'Tests run:|BUILD|ERROR' "$OUT/mvn-unit.log" | tail -10
mkdir -p "$OUT/surefire"
cp "$SRC/$MOD/target/surefire-reports/"*TestDumpWaterMark* "$OUT/surefire/" || fail "no surefire report"
run cat "$OUT/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt"
O=$OUT/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark-output.txt
[ -f "$O" ] || O=$OUT/mvn-unit.log
grep -E 'DUMPWM|nonSequentialWriteInMemory|Create dump file|Asking dumper|Got failure|Start dump|After dump|Dumper' "$O" > "$OUT/unit-trace.log"
grep -c 'Update nonSequentialWriteInMemory' "$OUT/unit-trace.log" | sed 's/^/DEBUG update lines: /'
grep 'DUMPWM' "$OUT/unit-trace.log" | grep -v ' ROW,' 
run ls -la "$R/unit-dump"
run jps -l
echo "=== unit tier end $(date '+%F %T %Z')"
