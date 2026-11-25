#!/usr/bin/env bash
# Unit tier (B2, with the audit amendments of 2026-11-25) for nfs.max.open.files-put-maxStreams--autonomous.
# Runs ON the node (pc75). Every command and its output goes to $R/logs/unit-run.log.
set -euo pipefail
R=/mydata/jingsong-s4/nfs.max.open.files-put-maxStreams-run1
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-nfs
TDIR=$SRC/$MOD/src/test/java/org/apache/hadoop/hdfs/nfs/nfs3
MAIN=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/nfs/nfs3
OUT=$R/logs/unit
mkdir -p "$OUT"
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
[ -z "$(git status --short | grep -v TestMaxOpenFilesMemory.java)" ] || fail "source copy not clean"
run sed -n 124p "$MAIN/OpenFileCtxCache.java"
sed -n 124p "$MAIN/OpenFileCtxCache.java" | grep -qF 'if (size() == this.maxStreams) {' || fail "line 124"
run sed -n 52,54p "$MAIN/OpenFileCtxCache.java"
run cp "$R/harness/TestMaxOpenFilesMemory.java" "$TDIR/"
rm -rf "$SRC/$MOD/target/surefire-reports"
run mvn -B -o test -pl "$MOD" -Dtest=TestMaxOpenFilesMemory -Dmaven.javadoc.skip=true \
    "-Dmaven-surefire-plugin.argLine=-Xmx1g" \
    > "$OUT/mvn-unit.log" 2>&1 || echo "mvn exit $? (surefire counts are read, not the exit code)"
run grep -E 'Tests run:|BUILD|ERROR' "$OUT/mvn-unit.log" | tail -15 || true
mkdir -p "$OUT/surefire"
cp "$SRC/$MOD/target/surefire-reports/"*TestMaxOpenFilesMemory* "$OUT/surefire/" || fail "no surefire report"
grep -hE '^(ROW|WSTATUS|STREAMERS)' "$OUT/surefire/"*-output.txt > "$OUT/readings.txt" || true
run cat "$OUT/readings.txt"
run cat "$OUT/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestMaxOpenFilesMemory.txt"
echo "--- log-line counts in the surefire output (whole JVM, all methods)"
for p in "Maximum open streams is" "Can't add new stream" "Can't add more stream" "All opened streams are busy" "Evict stream ctx"; do
  echo "$p: $(grep -cF "$p" "$OUT/surefire/"*-output.txt || true)"
done
echo "=== unit tier end $(date '+%F %T %Z')"
