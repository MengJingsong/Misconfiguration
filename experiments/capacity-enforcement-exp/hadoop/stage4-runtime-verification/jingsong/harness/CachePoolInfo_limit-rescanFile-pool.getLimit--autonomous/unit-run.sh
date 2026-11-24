#!/usr/bin/env bash
# Stage-4 unit tier (B2 + A1-A3) for CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous. Runs on pc75.
# Usage: unit-run.sh <harness-dir> [--compile-only]
# Logs every command and its output to $LOGS/unit-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:-}
STEM=CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src
LOGS=$RUNDIR/logs/unit
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
run java -version
run mvn -v | head -3
if [ ! -d "$SRC" ]; then
  echo "+ git -C $REPO status --short systems/hadoop/source"
  st=$(git -C "$REPO" status --short systems/hadoop/source); echo "${st:-<clean>}"
  [ -z "$st" ] || { echo "STOP: repository source not clean"; exit 1; }
  run "$REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh" "$SRC" || exit 1
fi
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestPoolLimitRescanCap.java
run cp "$H/TestPoolLimitRescanCap.java" "$T" || exit 1
run md5sum "$H/TestPoolLimitRescanCap.java" "$T"
run git -C "$SRC" status --short
cd "$SRC" || exit 1
if [ "$MODE" = "--compile-only" ]; then
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20
  exit 0
fi
run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestPoolLimitRescanCap -DfailIfNoTests=false \
  -Dmaven.javadoc.skip=true > "$LOGS/mvn-test.log" 2>&1
echo "mvn rc=$? (surefire counts are authoritative, not rc)"
grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/mvn-test.log" | tail -5
SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
run cp "$SR"/*TestPoolLimitRescanCap* "$LOGS/"
grep -h '^IFCHK' "$LOGS"/*TestPoolLimitRescanCap-output.txt > "$LOGS/ifchk.csv"
echo "IFCHK lines: $(wc -l < "$LOGS/ifchk.csv")"
cat "$LOGS/ifchk.csv"
echo "=== unit-run.sh end $(date '+%F %T %Z')"
