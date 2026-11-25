#!/usr/bin/env bash
# Unit tier (B2) for DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK--autonomous.
# Runs ON the node (pc82; the 2026-11-25 05:35 EST attempt on pc99 never started). Logs every command and its output to $R/logs/unit-run.log.
# Expects $R/src from copy-source.sh and $R/harness/TestDumpWaterMark.java.
set -euo pipefail
R=/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-waitForDump-DUMP_WRITE_WATER_MARK-run1
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
TDIR=$SRC/$MOD/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3
OFC=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3/OpenFileCtx.java
OUT=$R/logs/unit
LOG=$R/logs/unit-run.log
mkdir -p "$OUT" "$R/tmp/unit"
exec > >(tee -a "$LOG") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }

echo "=== unit tier start $(date '+%F %T %Z') on $(hostname)"
run java -version
run mvn -v | head -3 || true
cd "$SRC"
run git describe --tags
[ -z "$(git status --short | grep -v TestDumpWaterMark.java)" ] || fail "source copy not clean"
run sed -n 73p "$OFC"
grep -q 'private static long DUMP_WRITE_WATER_MARK = 1024 \* 1024;' <(sed -n 73p "$OFC") || fail "line 73 is not the declaration"
run sed -n 278p "$OFC"
grep -q 'if (nonSequentialWriteInMemory.get() < DUMP_WRITE_WATER_MARK) {' <(sed -n 278p "$OFC") || fail "line 278 is not the cited check"
run cp "$R/harness/TestDumpWaterMark.java" "$TDIR/"
rm -rf "$SRC/$MOD/target/surefire-reports" "$R/tmp/unit"/*
run mvn -B -o test -pl "$MOD" -Dtest=TestDumpWaterMark \
    "-Dmaven-surefire-plugin.argLine=-Xmx1g -Ddumpwm.tmp=$R/tmp/unit" \
    > "$OUT/mvn-unit.log" 2>&1 || echo "mvn exit $? (not read; surefire counts are read)"
run grep -E 'Tests run:|BUILD|ERROR' "$OUT/mvn-unit.log" | tail -12 || true
mkdir -p "$OUT/surefire"
cp "$SRC/$MOD/target/surefire-reports/"*TestDumpWaterMark* "$OUT/surefire/" || fail "no surefire report"
run grep -hE '^(ENV|KNOB|ROW|BLOCKED|BLOCKSTACK|SUMMARY|CLEANUP)' "$OUT/surefire/"*-output.txt > "$OUT/readings.csv" || true
run wc -l "$OUT/readings.csv"
run grep -E '^(SUMMARY|BLOCKED|CLEANUP)' "$OUT/readings.csv"
run cat "$OUT/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt"
run ls -la "$R/tmp/unit"
run cp "$R"/tmp/unit/*-openfilectx.log "$OUT/" || true
echo "=== unit tier end $(date '+%F %T %Z')"
