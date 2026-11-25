#!/usr/bin/env bash
# Unit tier (B2 with A1, A2, A3, A8, A9) for
# dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.
# Runs ON the node (pc75). Logs every command and its output to $R/logs/unit-run.log.
# Usage: unit-run.sh   (expects $R/src from copy-source.sh and $R/harness/ with the test class)
set -euo pipefail
R=/mydata/jingsong-s4/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated-run1
SRC=$R/src
MOD=hadoop-hdfs-project/hadoop-hdfs-client
TDIR=$SRC/$MOD/src/test/java/org/apache/hadoop/hdfs/util
BAM=$SRC/$MOD/src/main/java/org/apache/hadoop/hdfs/util/ByteArrayManager.java
OUT=$R/logs/unit
LOG=$R/logs/unit-run.log
mkdir -p "$OUT"
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
[ -z "$(git diff --stat)" ] || fail "source copy not clean"
run sed -n 209p "$BAM"
grep -q 'if (freeQueue.size() < maxAllocated - numAllocated) {' <(sed -n 209p "$BAM") || fail "line 209 is not the cited check"
run cp "$R/harness/TestByteArrayManagerCountLimitPool.java" "$TDIR/"

one_mode() {
  local mode=$1
  echo "=== mode $mode $(date '+%F %T %Z')"
  rm -rf "$SRC/$MOD/target/surefire-reports"
  run mvn -B test -pl "$MOD" -Dtest=TestByteArrayManagerCountLimitPool \
      "-Dmaven-surefire-plugin.argLine=-Xmx1g -XX:+UseSerialGC -Dbam.mode=$mode" \
      > "$OUT/mvn-$mode.log" 2>&1 || echo "mvn exit $? (not read; surefire counts are read)"
  run grep -E 'Tests run:|BUILD|ERROR' "$OUT/mvn-$mode.log" | tail -8 || true
  mkdir -p "$OUT/surefire-$mode"
  cp "$SRC/$MOD/target/surefire-reports/"*TestByteArrayManagerCountLimitPool* "$OUT/surefire-$mode/" \
      || fail "no surefire report for $mode"
  run grep -hE '^(ENV|SETTLE|KNOWN|CASE1|CASE2|CASE3|WIRE|CHILD-EXIT|CHILD-CP)' \
      "$OUT/surefire-$mode/"*-output.txt > "$OUT/readings-$mode.csv" || true
  run wc -l "$OUT/readings-$mode.csv"
  run cat "$OUT/surefire-$mode/org.apache.hadoop.hdfs.util.TestByteArrayManagerCountLimitPool.txt"
}

one_mode managed
one_mode disabled

echo "=== mutation: line 209 -> if (true) {"
run sed -i '209s/if (freeQueue.size() < maxAllocated - numAllocated) {/if (true) {/' "$BAM"
run git diff --stat
run sed -n 209p "$BAM"
grep -q 'if (true) {' <(sed -n 209p "$BAM") || fail "mutation not applied"
one_mode mutation
run git checkout -- "$BAM"
[ -z "$(git diff --stat)" ] || fail "revert failed"
run git diff --stat
run git status --short
echo "=== recompile the reverted class into the copy's target/classes (never installed)"
run mvn -B -q compile -pl "$MOD" > "$OUT/mvn-recompile.log" 2>&1 || fail "recompile failed"
echo "=== unit tier end $(date '+%F %T %Z')"
