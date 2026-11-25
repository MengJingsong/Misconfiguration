#!/usr/bin/env bash
# Stage-4 unit tier (B2 + A1-A5) for dfs.client.mmap.cache.size-...--autonomous. Runs on pc91.
# Usage: unit-run.sh <harness-dir> [--compile-only]. Every command and its output -> $LOGS/unit-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:-}
STEM=dfs.client.mmap.cache.size-demoteOldEvictableMmaped-maxEvictableMmapedSize--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src
LOGS=$RUNDIR/logs/unit
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
run java -version
[ -d "$SRC" ] || { echo "STOP: no source copy (prep.sh)"; exit 1; }
run ls -l "$SRC/hadoop-common-project/hadoop-common/target/native/target/usr/local/lib/" || { echo "STOP: no native lib"; exit 1; }
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/fs/TestMmapCacheSizeCap.java
run cp "$H/TestMmapCacheSizeCap.java" "$T" || exit 1
run md5sum "$H/TestMmapCacheSizeCap.java" "$T"
run git -C "$SRC" status --short
cd "$SRC" || exit 1
if [ "$MODE" = "--compile-only" ]; then
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20
  exit 0
fi
run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestMmapCacheSizeCap -DfailIfNoTests=false \
  -Dmaven.javadoc.skip=true > "$LOGS/mvn-test.log" 2>&1
echo "mvn rc=$? (surefire counts are authoritative, not rc)"
grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/mvn-test.log" | tail -5
SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
run cp "$SR"/*TestMmapCacheSizeCap* "$LOGS/"
grep -h '^IFCHK' "$LOGS"/*TestMmapCacheSizeCap-output.txt > "$LOGS/ifchk.txt"
echo "IFCHK lines: $(wc -l < "$LOGS/ifchk.txt")"
grep -E 'step=(after-close|end)|IFCHK,env' "$LOGS/ifchk.txt"
echo "+ leftover JVM check:"; ps -eo pid,cmd | grep -E '[s]urefire' | grep "$RUNDIR" | cut -c1-150 || echo "  no surefire JVM of this run"
echo "=== unit-run.sh end $(date '+%F %T %Z')"
