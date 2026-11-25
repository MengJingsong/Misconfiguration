#!/usr/bin/env bash
# Stage-4 unit tier (B2 + A1-A3) for dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.
# Runs on pc82. Usage: unit-run.sh <harness-dir> compile|run|mutant
#   compile: copy the test class into the case copy and test-compile hadoop-hdfs (instrument check)
#   run:     unmutated rows testC* (C = 0, 16384, 32768, 65536, small control)
#   mutant:  line 745 of CacheReplicationMonitor disabled in the case copy, mutantC32768 only, then restored
# Logs every command and its output to $LOGS/unit-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous
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
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCacheCapacityCheck.java
CRM=hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
run cp "$H/TestCacheCapacityCheck.java" "$T" || exit 1
run md5sum "$H/TestCacheCapacityCheck.java" "$T"
cd "$SRC" || exit 1
run sed -n 745p "$CRM"
run git -C "$SRC" status --short
mvntest() {  # $1 = -Dtest selector, $2 = log name
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest="$1" -DfailIfNoTests=false \
    -Dtest.build.data="$TD" -Dmaven.javadoc.skip=true > "$LOGS/$2.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)|Changes detected|Compiling" "$LOGS/$2.log" | tail -8
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/$2-surefire"
  run cp "$SR"/*TestCacheCapacityCheck* "$LOGS/$2-surefire/"
  grep -h '^IFCHK' "$LOGS/$2-surefire/"*TestCacheCapacityCheck-output.txt > "$LOGS/$2-ifchk.csv"
  echo "IFCHK lines: $(wc -l < "$LOGS/$2-ifchk.csv")"; cat "$LOGS/$2-ifchk.csv"
}
case "$MODE" in
compile)
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20 ;;
run)
  mvntest 'TestCacheCapacityCheck#testC*' unmutated ;;
mutant)
  run git -C "$SRC" diff --stat
  [ -z "$(git -C "$SRC" diff --name-only)" ] || { echo "STOP: tracked files already modified"; exit 1; }
  run sed -i '745s/if (pendingCapacity < blockInfo.getNumBytes()) {/if (false \&\& pendingCapacity < blockInfo.getNumBytes()) {/' "$CRM"
  run git -C "$SRC" diff -- "$CRM" | tee "$LOGS/mutation.diff"
  grep -q 'if (false && pendingCapacity' "$CRM" || { echo "STOP: mutation not applied"; exit 1; }
  mvntest 'TestCacheCapacityCheck#mutantC32768' mutant
  run git -C "$SRC" checkout -- "$CRM"
  run sed -n 745p "$CRM"
  run git -C "$SRC" diff --stat ;;
esac
run du -sh "$TD"
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
