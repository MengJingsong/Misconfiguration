#!/usr/bin/env bash
# Stage-4 unit tier (B2 as amended D1-1..D1-3) for dfs.datanode.du.reserved-append-getAvailable--autonomous
# (queue order 28, Jingsong). Runs on pc72. Usage: unit-run.sh compile|run|umount
#   compile: copy the test class into the case copy and test-compile hadoop-hdfs (instrument check)
#   run:     fresh 2 GiB ext2 -m 0 image, mount, stat -f check, mvn test, collect O28 lines, unmount
#   umount:  unmount the unit image (idempotent)
set -uo pipefail
MODE=${1:?mode}
RUNDIR=/mydata/jingsong-s4/dfs.datanode.du.reserved-append-getAvailable-run1
H=$RUNDIR/harness
SRC=$RUNDIR/src
U=$RUNDIR/unit
LOGS=$RUNDIR/logs/unit
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
mkdir -p "$LOGS" "$U"
exec > >(tee -a "$LOGS/unit-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
umount_img() { if mountpoint -q "$U/mnt"; then run sudo umount "$U/mnt"; fi; losetup -a | grep "$U/vol.img" || echo "  no loop device on $U/vol.img"; }
echo "=== unit-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"
[ -d "$SRC/.git" ] || { echo "STOP: no source copy $SRC"; exit 1; }
T=$SRC/hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/datanode/fsdataset/impl/TestAppendDuReservedBoundary.java
case "$MODE" in
compile)
  run java -version
  run cp "$H/TestAppendDuReservedBoundary.java" "$T" || exit 1
  run md5sum "$H/TestAppendDuReservedBoundary.java" "$T"
  run git -C "$SRC" status --short
  cd "$SRC" || exit 1
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test-compile -Dmaven.javadoc.skip=true > "$LOGS/compile.log" 2>&1
  echo "compile rc=$?"; grep -E "BUILD (SUCCESS|FAILURE)|ERROR" "$LOGS/compile.log" | head -20 ;;
run)
  trap umount_img EXIT
  run cmp "$H/TestAppendDuReservedBoundary.java" "$T" || exit 1
  umount_img
  run rm -rf "$U/mnt" "$U/snap" "$U/vol.img"
  run mkdir -p "$U/mnt" "$U/snap"
  run truncate -s 2G "$U/vol.img"
  run mkfs.ext2 -q -F -m 0 "$U/vol.img" || exit 1
  run sudo mount -o loop "$U/vol.img" "$U/mnt" || exit 1
  run sudo chown "$(id -u):$(id -g)" "$U/mnt"
  run stat -f "$U/mnt"
  read FREE AVAIL < <(stat -f -c '%f %a' "$U/mnt")
  [ "$FREE" = "$AVAIL" ] || { echo "STOP: Free $FREE != Available $AVAIL"; exit 1; }
  echo "  stat -f check: Free == Available ($FREE)"
  run df -B1 --output=size,used,avail "$U/mnt"
  cd "$SRC" || exit 1
  run mvn -B -o -pl hadoop-hdfs-project/hadoop-hdfs test -Dtest=TestAppendDuReservedBoundary -DfailIfNoTests=false \
    -DtrimStackTrace=false -Do28.base="$U/mnt/mdfs" -Do28.snap="$U/snap/mdfs" \
    -Dmaven-surefire-plugin.argLine="-Xmx1g -Do28.base=$U/mnt/mdfs -Do28.snap=$U/snap/mdfs" \
    -Dmaven.javadoc.skip=true > "$LOGS/test.log" 2>&1
  echo "mvn rc=$? (surefire counts are authoritative, not rc)"
  grep -E "Tests run:|BUILD (SUCCESS|FAILURE)" "$LOGS/test.log" | tail -5
  SR=$SRC/hadoop-hdfs-project/hadoop-hdfs/target/surefire-reports
  mkdir -p "$LOGS/surefire"
  run cp "$SR"/*TestAppendDuReservedBoundary* "$LOGS/surefire/"
  OUT=$(ls "$LOGS/surefire/"*TestAppendDuReservedBoundary-output.txt)
  grep -h '^O28,' "$OUT" > "$LOGS/o28-readings.csv"
  echo "O28 lines: $(wc -l < "$LOGS/o28-readings.csv")"
  grep -E 'calib|summary|sh,.*rc=[1-9]' "$LOGS/o28-readings.csv"
  echo "--- 'Insufficient space for appending to' lines (count):"
  grep -c 'Insufficient space for appending to' "$OUT"
  grep -h 'Insufficient space for appending to' "$OUT" | cut -c1-260 > "$LOGS/insufficient-lines.txt"
  echo "--- 'Appending to' (FsDatasetImpl.append attempts):"
  grep -c 'Appending to' "$OUT"
  echo "--- other gates (Out of space / could only be written to):"
  grep -cE 'Out of space|could only be written to' "$OUT"
  run df -B1 --output=size,used,avail "$U/mnt"
  run du -sh "$U/mnt" "$U/snap" ;;
umount)
  umount_img ;;
esac
echo "=== unit-run.sh $MODE end $(date '+%F %T %Z')"
