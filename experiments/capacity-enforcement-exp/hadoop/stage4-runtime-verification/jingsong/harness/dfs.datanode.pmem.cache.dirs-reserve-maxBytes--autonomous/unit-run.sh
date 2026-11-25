#!/usr/bin/env bash
# Stage-4 unit tier (B2 + S1-S3) for dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous. Runs on pc82.
# Usage: unit-run.sh copy|compile|run
#   copy:    copy-source.sh into $RUN/src (once)
#   compile: put the test class into the copy and test-compile hadoop-hdfs (instrument check)
#   run:     run TestPmemCapacityCap (all u1*, u2*, u3* methods, name order)
# Logs every command and its output to $LOGS/unit-run.log (append).
set -uo pipefail
MODE=${1:?mode}
RUN=/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1
H=$RUN/harness
SRC=$RUN/src
LOGS=$RUN/logs/unit
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
PKG=hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl
case "$MODE" in
copy)
  run git -C "$REPO" status --short systems/hadoop/source
  [ -z "$(git -C "$REPO" status --short systems/hadoop/source)" ] || { echo "STOP: repo source not clean"; exit 1; }
  run git -C "$REPO" log -1 --format='%h %ci'
  run "$REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh" "$SRC" ;;
compile)
  [ -d "$SRC/.git" ] || { echo "STOP: no source copy $SRC"; exit 1; }
  run java -version
  run cp "$H/TestPmemCapacityCap.java" "$SRC/$PKG/TestPmemCapacityCap.java" || exit 1
  run md5sum "$H/TestPmemCapacityCap.java" "$SRC/$PKG/TestPmemCapacityCap.java"
  run git -C "$SRC" status --short
  cd "$SRC" || exit 1
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR|Total time" "$LOGS/compile.log" | head -20 ;;
run)
  cd "$SRC" || exit 1
  run git -C "$SRC" status --short
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestPmemCapacityCap -DfailIfNoTests=false \
      -Dmaven.javadoc.skip=true > "$LOGS/test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)|Total time" "$LOGS/test.log" | tail -6
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/surefire"
  run cp "$SR"/*TestPmemCapacityCap* "$LOGS/surefire/"
  grep -h '^PMCHK' "$LOGS/surefire/"*TestPmemCapacityCap-output.txt > "$LOGS/pmchk.csv"
  echo "PMCHK lines: $(wc -l < "$LOGS/pmchk.csv")"; cat "$LOGS/pmchk.csv"
  run du -sh "$SRC/hadoop-hdfs-project/hadoop-hdfs/target/test" ;;
esac
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
