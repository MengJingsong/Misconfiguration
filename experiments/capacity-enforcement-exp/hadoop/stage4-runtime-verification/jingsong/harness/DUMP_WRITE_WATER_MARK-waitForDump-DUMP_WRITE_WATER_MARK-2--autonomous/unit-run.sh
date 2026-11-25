#!/usr/bin/env bash
# Unit tier (B2) for DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2--autonomous.
# Runs ON the node (pc72). Every command and its output goes to $R/logs/unit-run.log.
set -euo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-2-run1
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
TDIR=$SRC/$MOD/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
OUT=$R/logs/unit
mkdir -p "$OUT" "$R/tmp/unit"
exec > >(tee -a "$R/logs/unit-run.log") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }

echo "=== unit tier start $(date '+%F %T %Z') on $(hostname)"
run java -version
run mvn -v
cd "$SRC"
run git describe --tags
[ -z "$(git status --short | grep -v TestDumpWaterMark.java)" ] || fail "source copy not clean"
run sed -n 73p "$OFC"
sed -n 73p "$OFC" | grep -q 'private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;' || fail "line 73"
run sed -n 284p "$OFC"
sed -n 284p "$OFC" | grep -q 'if (nonSequentialWriteInMemory.get() >= DUMP_WRITE_WATER_MARK) {' || fail "line 284"
run cp "$R/harness/TestDumpWaterMark.java" "$TDIR/"
rm -rf "$SRC/$MOD/target/surefire-reports" "$R/tmp/unit"/*
run mvn -B -o test -pl "$MOD" -Dtest=TestDumpWaterMark -Dmaven.javadoc.skip=true \
    "-Dmaven-surefire-plugin.argLine=-Xmx512m -Ddumpwm.tmp=$R/tmp/unit" \
    > "$OUT/mvn-unit.log" 2>&1 || echo "mvn exit $? (surefire counts are read, not the exit code)"
run grep -E 'Tests run:|BUILD|ERROR' "$OUT/mvn-unit.log" | tail -15 || true
mkdir -p "$OUT/surefire"
cp "$SRC/$MOD/target/surefire-reports/"*TestDumpWaterMark* "$OUT/surefire/" || fail "no surefire report"
grep -hE '^(ENV|KNOB|ROW|BLOCKED|SUMMARY|PROBE2|CLEANUP|SEQ)' "$OUT/surefire/"*-output.txt > "$OUT/readings.csv" || true
run wc -l "$OUT/readings.csv"
run grep -E '^(ENV|SUMMARY|BLOCKED|PROBE2|CLEANUP|SEQ)' "$OUT/readings.csv"
run cat "$OUT/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt"
run ls -la "$R/tmp/unit"
echo "=== unit tier end $(date '+%F %T %Z')"
