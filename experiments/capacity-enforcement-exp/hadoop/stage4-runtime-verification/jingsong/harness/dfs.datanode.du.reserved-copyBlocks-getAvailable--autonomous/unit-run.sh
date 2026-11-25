#!/usr/bin/env bash
# Stage-4 unit tier (B2, amended D1-1/D1-2/D1-5) for
# dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous (Jingsong queue order 26). Runs on pc91.
# Usage: unit-run.sh <harness-dir> compile|run
#   compile: copy the test class into the case copy and test-compile hadoop-hdfs offline (instrument check)
#   run:     mvn -o test -Dtest=TestDiskBalancerDestReserve; save surefire output; extract O26 lines and,
#            per run (O26-BEGIN/END markers), the DiskBalancer stop lines (1148 / 1110 / 1121 / 1102)
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
RUNDIR=/mydata/jingsong-s4/dfs.datanode.du.reserved-copyBlocks-getAvailable-run1
SRC=$RUNDIR/src
LOGS=$RUNDIR/logs/unit
TD=$RUNDIR/test-data
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS" "$TD"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
[ -d "$SRC/.git" ] || { echo "STOP: no source copy $SRC"; exit 1; }
run java -version
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/diskbalancer/TestDiskBalancerDestReserve.java
run cp "$H/TestDiskBalancerDestReserve.java" "$T" || exit 1
run md5sum "$H/TestDiskBalancerDestReserve.java" "$T"
cd "$SRC" || exit 1
run git -C "$SRC" status --short
run sed -n 1136,1153p hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/DiskBalancer.java
run df -B1 --output=size,used,avail "$TD"
case "$MODE" in
compile)
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20 ;;
run)
  rm -rf "$TD/o26"
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestDiskBalancerDestReserve -DfailIfNoTests=false \
    -DtrimStackTrace=false -Dtest.build.data="$TD" -Dmaven.javadoc.skip=true > "$LOGS/test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/test.log" | tail -5
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/surefire"
  run cp "$SR"/*TestDiskBalancerDestReserve* "$LOGS/surefire/"
  OUT=$(ls "$LOGS/surefire/"*TestDiskBalancerDestReserve-output.txt)
  grep -h '^O26' "$OUT" > "$LOGS/o26-readings.txt"
  echo "O26 lines: $(wc -l < "$LOGS/o26-readings.txt")"
  grep -E ',(step5|step7|result),' "$LOGS/o26-readings.txt"
  echo "--- DiskBalancer stop lines per run (1148 enough space / 1110 done / 1121 no source / 1102 max error):"
  awk '/^O26-BEGIN/{run=$2} /^O26-END/{run=""} run!="" && /does not have enough space|Copy from .* done|No source blocks|Exceeded the max error count|No movable source blocks/{print run": "$0}' "$OUT" \
    | sed -E 's/^(U[0-9]): .*(DiskBalancer[^ ]*) /\1: \2 /' | tee "$LOGS/stop-lines.txt" | cut -c1-260
  echo "--- counts per run:"
  for u in U0 U1 U2 U3 U4; do
    printf '%s 1148=%s 1110=%s 1121=%s 1102=%s\n' $u \
      "$(grep -c "^$u: .*does not have enough space" "$LOGS/stop-lines.txt")" \
      "$(grep -c "^$u: .*Copy from .* done" "$LOGS/stop-lines.txt")" \
      "$(grep -c "^$u: .*No source blocks" "$LOGS/stop-lines.txt")" \
      "$(grep -c "^$u: .*Exceeded the max error" "$LOGS/stop-lines.txt")"
  done ;;
esac
run du -sh "$TD"
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
