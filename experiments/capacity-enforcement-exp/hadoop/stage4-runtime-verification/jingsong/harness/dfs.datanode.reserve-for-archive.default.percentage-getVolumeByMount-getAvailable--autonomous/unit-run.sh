#!/usr/bin/env bash
# Order 29 stage-4 unit tier (B2 with D1-1..D1-4). Runs on pc91. Usage: unit-run.sh <harness-dir> compile|run
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
RUN=/mydata/jingsong-s4/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable-run1
SRC=$RUN/src; LOGS=$RUN/logs/unit; MNT=$RUN/mnt; TD=$MNT/testdata
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
mountpoint -q "$MNT" || { echo "STOP: $MNT is not mounted"; exit 1; }
run java -version
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestArchiveSameMountCap.java
run cp "$H/TestArchiveSameMountCap.java" "$T" || exit 1
run md5sum "$H/TestArchiveSameMountCap.java" "$T"
cd "$SRC" || exit 1
run git -C "$SRC" status --short
run sed -n 140,152p hadoop-hdfs-project/hadoop-hdfs/src/main/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/FsVolumeList.java
run df -B1 "$MNT"
case "$MODE" in
compile)
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20 ;;
run)
  mkdir -p "$TD"
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestArchiveSameMountCap -DfailIfNoTests=false \
    -DtrimStackTrace=false -Dtest.build.data="$TD" -Dhdfs.minidfs.basedir="$TD/minidfs" \
    -Dmaven.javadoc.skip=true > "$LOGS/test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/test.log" | tail -5
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/surefire"
  run cp "$SR"/*TestArchiveSameMountCap* "$LOGS/surefire/"
  grep -h '^O29,' "$LOGS/surefire/"*TestArchiveSameMountCap-output.txt > "$LOGS/o29-readings.csv"
  echo "O29 lines: $(wc -l < "$LOGS/o29-readings.csv")"
  grep -E ',(sanity|summary),' "$LOGS/o29-readings.csv"
  echo "--- fallback WARN lines (count):"; grep -h 'is less than the block size' "$LOGS/surefire/"*-output.txt | wc -l
  run du -sh "$TD"; run rm -rf "$TD" ;;
esac
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
