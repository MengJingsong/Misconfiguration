#!/usr/bin/env bash
# Stage-4 unit tier (B2 + A1-A4) for dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.
# Runs on pc99. Usage: unit-run.sh <harness-dir> compile|test|ablate
#   compile: make the case copy (copy-source.sh), add the test, test-compile hadoop-hdfs
#   test:    run TestCrmPendingFit (all 12 methods) in the case copy
#   ablate:  second copy src-ablate, line 534 -> if (false && ...), run testB_U49152 there (B2e step 4)
# Every command and its output is logged to $LOGS/unit-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src
ABL=$RUNDIR/src-ablate
LOGS=$RUNDIR/logs/unit
REPO=/proj/misconfiguration-PG0/git-repos/Misconfiguration
CP=$REPO/experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/jingsong/copy-source.sh
CRM=hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/blockmanagement/CacheReplicationMonitor.java
TREL=hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/namenode/TestCrmPendingFit.java
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
mkcopy() {  # $1 = target dir
  if [ ! -d "$1" ]; then
    echo "+ git -C $REPO status --short systems/hadoop/source"
    st=$(git -C "$REPO" status --short systems/hadoop/source); echo "${st:-<clean>}"
    [ -z "$st" ] || { echo "STOP: repository source not clean"; exit 1; }
    run "$CP" "$1" || exit 1
  fi
  run cp "$H/TestCrmPendingFit.java" "$1/$TREL" || exit 1
  run md5sum "$H/TestCrmPendingFit.java" "$1/$TREL"
}
case "$MODE" in
compile)
  run java -version
  run mvn -v
  mkcopy "$SRC"
  run git -C "$SRC" status --short
  cd "$SRC" || exit 1
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR|Total time" "$LOGS/compile.log" | head -20
  ;;
test)
  cd "$SRC" || exit 1
  run git -C "$SRC" status --short
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestCrmPendingFit -DfailIfNoTests=false \
    -Dmaven.javadoc.skip=true > "$LOGS/mvn-test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/mvn-test.log" | tail -5
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  run cp "$SR"/*TestCrmPendingFit* "$LOGS/"
  grep -h '^IFCHK' "$LOGS"/*TestCrmPendingFit-output.txt > "$LOGS/ifchk.csv"
  echo "IFCHK lines: $(wc -l < "$LOGS/ifchk.csv")"; cat "$LOGS/ifchk.csv"
  ;;
ablate)
  mkcopy "$ABL"
  echo "+ line 534 before:"; sed -n 534p "$ABL/$CRM"
  grep -q 'if (blockInfo.getNumBytes() > remaining) {' "$ABL/$CRM" || { echo "STOP: line text not found"; exit 1; }
  run sed -i '534s/if (blockInfo.getNumBytes() > remaining) {/if (false \&\& blockInfo.getNumBytes() > remaining) {/' "$ABL/$CRM"
  echo "+ line 534 after:"; sed -n 534p "$ABL/$CRM"
  run git -C "$ABL" diff --stat
  git -C "$ABL" diff > "$LOGS/ablate.diff"; cat "$LOGS/ablate.diff"
  cd "$ABL" || exit 1
  mkdir -p "$LOGS/ablate"
  run mvn -B -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest='TestCrmPendingFit#testB_U49152' -DfailIfNoTests=false \
    -Dmaven.javadoc.skip=true > "$LOGS/ablate/mvn-test.log" 2>&1
  echo "mvn rc=$?"; grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/ablate/mvn-test.log" | tail -5
  SR=$ABL/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  run cp "$SR"/*TestCrmPendingFit* "$LOGS/ablate/"
  grep -h '^IFCHK' "$LOGS"/ablate/*TestCrmPendingFit-output.txt > "$LOGS/ablate/ifchk.csv"
  cat "$LOGS/ablate/ifchk.csv"
  ;;
esac
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
