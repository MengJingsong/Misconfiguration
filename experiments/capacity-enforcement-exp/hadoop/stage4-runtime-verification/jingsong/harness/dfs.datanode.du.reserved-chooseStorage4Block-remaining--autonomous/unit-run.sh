#!/usr/bin/env bash
# Stage-4 unit tier (B2) for dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous (order 25).
# Runs on pc75. Usage: unit-run.sh <harness-dir> compile|run
#   compile: copy the test class into the case copy and test-compile hadoop-hdfs (instrument check)
#   run:     mvn test -Dtest=TestChooseStorage4BlockReserved, save surefire output and O25 lines
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
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
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestChooseStorage4BlockReserved.java
run cp "$H/TestChooseStorage4BlockReserved.java" "$T" || exit 1
run md5sum "$H/TestChooseStorage4BlockReserved.java" "$T"
cd "$SRC" || exit 1
run git -C "$SRC" status --short
run sed -n 816,841p hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/DatanodeDescriptor.java
run df -B1 --output=size,used,avail "$TD"
case "$MODE" in
compile)
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20 ;;
run)
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestChooseStorage4BlockReserved -DfailIfNoTests=false \
    -DtrimStackTrace=false -Dtest.build.data="$TD" -Dhdfs.minidfs.basedir="$TD/minidfs" \
    -Dmaven.javadoc.skip=true > "$LOGS/test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/test.log" | tail -5
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/surefire"
  run cp "$SR"/*TestChooseStorage4BlockReserved* "$LOGS/surefire/"
  grep -h '^O25,' "$LOGS/surefire/"*TestChooseStorage4BlockReserved-output.txt > "$LOGS/o25-readings.csv"
  echo "O25 lines: $(wc -l < "$LOGS/o25-readings.csv")"
  grep -E 'summary|,start,|,pre,|SKIP' "$LOGS/o25-readings.csv"
  echo "--- NN 'Not enough replicas' lines (count, distinct):"
  grep -h 'Not enough replicas was chosen' "$LOGS/surefire/"*-output.txt | sed 's/^.*Reason/Reason/' | sort | uniq -c
  echo "--- check DEBUG 'does not have enough' lines by thread (NameNode IPC handler = real placement path):"
  grep -h 'does not have enough' "$LOGS/surefire/"*-output.txt | grep -c 'IPC Server handler'
  grep -h 'does not have enough' "$LOGS/surefire/"*-output.txt | grep -vc 'IPC Server handler'
  grep -h 'does not have enough' "$LOGS/surefire/"*-output.txt | grep 'IPC Server handler' > "$LOGS/nn-check-debug-lines.txt"
  echo "--- 'could only be written to' (count):"
  grep -h 'could only be written to' "$LOGS/surefire/"*-output.txt | wc -l
  echo "--- DataNode out-of-space lines (count):"
  grep -hE 'DiskOutOfSpaceException|Out of space' "$LOGS/surefire/"*-output.txt | wc -l ;;
esac
run du -sh "$TD"
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
