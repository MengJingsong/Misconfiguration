#!/usr/bin/env bash
# Stage-4 unit tier (B2, as amended D1-1/D1-2) for
# dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous (queue order 27). Runs on pc82.
# Usage: unit-run.sh <harness-dir> copy|compile|run
#   copy:    copy-source.sh into <run>/src (B2e step 1, D1-1)
#   compile: put the test class in the copy and test-compile hadoop-hdfs offline (instrument check)
#   run:     mvn test -Dtest=TestDuReservedAvailableSpacePlacement; save surefire output and CSV lines (B2e 3-4)
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration
RUNDIR=/mydata/jingsong-s4/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes-run1
SRC=$RUNDIR/src
LOGS=$RUNDIR/logs/unit
TD=$RUNDIR/test-data
CLS=TestDuReservedAvailableSpacePlacement
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS" "$TD"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/$CLS.java
case "$MODE" in
copy)
  run git -C "$REPO" status --short systems/hadoop/source
  run git -C "$REPO" rev-parse --short HEAD
  run "$REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh" "$SRC" ;;
compile)
  [ -d "$SRC/.git" ] || { echo "STOP: no source copy $SRC"; exit 1; }
  run java -version
  run cp "$H/$CLS.java" "$T" || exit 1
  run md5sum "$H/$CLS.java" "$T"
  run git -C "$SRC" status --short
  cd "$SRC" || exit 1
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20 ;;
run)
  [ -f "$T" ] || { echo "STOP: test class not in copy"; exit 1; }
  run md5sum "$H/$CLS.java" "$T"
  cd "$SRC" || exit 1
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=$CLS -DfailIfNoTests=false \
    -DtrimStackTrace=false -Dtest.build.data="$TD" -Dmaven.javadoc.skip=true > "$LOGS/test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/test.log" | tail -5
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/surefire"
  run cp "$SR"/*$CLS* "$LOGS/surefire/"
  grep -h '^CSV' "$LOGS/surefire/"*$CLS-output.txt > "$LOGS/u-results.csv"
  echo "CSV lines: $(wc -l < "$LOGS/u-results.csv")"
  # policy DEBUG lines and log lines in file order, interleaved with the CSV rows (same thread, same stream)
  grep -hE '^CSV|Volumes are imbalanced|All volumes are within|Out of space|less than the block size|Available space volume choosing policy initialized' \
    "$LOGS/surefire/"*$CLS-output.txt > "$LOGS/u-sequence.txt"
  echo "sequence lines: $(wc -l < "$LOGS/u-sequence.txt")" ;;
esac
run du -sh "$TD"
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
