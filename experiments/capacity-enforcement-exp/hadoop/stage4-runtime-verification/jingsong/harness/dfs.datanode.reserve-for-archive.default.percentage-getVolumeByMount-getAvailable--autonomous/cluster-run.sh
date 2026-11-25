#!/usr/bin/env bash
# Order 29 stage-4 cluster tier (B3 with D1-5, D1-6). Runs on pc91.
# Usage: cluster-run.sh <cfg>   cfg: r000 r010 r025 r050 (serial), c010 c025 (Mover concurrency default), ctl (tiering off, r=0.1)
#        cluster-run.sh stop    (stop daemons of the last cfg)
set -uo pipefail
CFG=${1:?cfg}
RUN=/mydata/jingsong-s4/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable-run1
CR=$RUN/cluster; MNT=$RUN/mnt
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$CR/hadoop PATH=$CR/hadoop/bin:/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
export HADOOP_PID_DIR=$CR/pids HADOOP_HEAPSIZE_MAX=1g HADOOP_CONF_DIR=$CR/conf
DNJMX=http://127.0.0.1:19864/jmx; NNJMX=http://127.0.0.1:19870/jmx
C=8589934592
stopall() {
  [ -n "${SAMPLER:-}" ] && kill "$SAMPLER" 2>/dev/null
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null
  sleep 2
  ps -u "$(id -un)" -o pid=,args= | awk '/proc_namenode|proc_datanode|org.apache.hadoop.hdfs.server.mover.Mover/ && !/awk/'
}
if [ "$CFG" = stop ]; then export HADOOP_LOG_DIR=$RUN/logs/cluster/stop; stopall; exit 0; fi
case "$CFG" in
  r000) R_=0.0; TIER=true; CONC=1;; r010) R_=0.1; TIER=true; CONC=1;; r025) R_=0.25; TIER=true; CONC=1;;
  r050) R_=0.5; TIER=true; CONC=1;; c010) R_=0.1; TIER=true; CONC=;; c025) R_=0.25; TIER=true; CONC=;;
  ctl) R_=0.1; TIER=false; CONC=1;; *) echo "bad cfg"; exit 2;;
esac
L=$RUN/logs/cluster/$CFG; mkdir -p "$L" "$CR/pids" "$CR/tmp"
export HADOOP_LOG_DIR=$L
exec > >(tee -a "$L/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
trap 'echo "EXIT trap: stopping"; stopall' EXIT
echo "=== cluster-run.sh $CFG start $(date '+%F %T %Z') host=$(hostname) r=$R_ tiering=$TIER conc=${CONC:-default}"
mountpoint -q "$MNT" || { echo "STOP: $MNT not mounted"; exit 1; }
if ps -u "$(id -un)" -o args= | awk '/proc_namenode|proc_datanode/ && !/awk/' | grep -q .; then echo "STOP: daemons already running"; exit 1; fi
[ -x "$CR/hadoop/bin/hdfs" ] || { mkdir -p "$CR"; run cp -a "$DIST" "$CR/hadoop" || exit 1; }
[ -f "$CR/blk.bin" ] || { echo "+ head -c 67108864 /dev/urandom > blk.bin"; head -c 67108864 /dev/urandom > "$CR/blk.bin"; }
[ "$(stat -c %s "$CR/blk.bin")" = 67108864 ] || { echo "STOP: blk.bin is not 67108864 B"; exit 1; }
# fresh state (B3e step 2)
run rm -rf "$CR/nn" "$MNT/dn" "$CR/tmp"; mkdir -p "$MNT/dn/disk" "$MNT/dn/archive" "$CR/tmp"
DFCAP=$(df -B1 --output=size "$MNT" | tail -1); RES=$((DFCAP - C))
echo "DFCAP=$DFCAP du.reserved=$RES C=$C"; run df -B1 "$MNT"
rm -rf "$CR/conf"; cp -r "$CR/hadoop/etc/hadoop" "$CR/conf"
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
{ echo '<?xml version="1.0"?><configuration>'; prop fs.defaultFS hdfs://localhost:19000; prop hadoop.tmp.dir "$CR/tmp"; echo '</configuration>'; } > "$CR/conf/core-site.xml"
{ echo '<?xml version="1.0"?><configuration>'
  prop dfs.replication 1; prop dfs.namenode.name.dir "file://$CR/nn"
  prop dfs.datanode.data.dir "[DISK]file://$MNT/dn/disk,[ARCHIVE]file://$MNT/dn/archive"
  prop dfs.datanode.same-disk-tiering.enabled "$TIER"; prop dfs.datanode.reserve-for-archive.default.percentage "$R_"
  prop dfs.datanode.du.reserved "$RES"; prop dfs.blocksize 67108864
  prop dfs.heartbeat.interval 1; prop dfs.namenode.redundancy.interval.seconds 1
  prop dfs.namenode.http-address 127.0.0.1:19870; prop dfs.namenode.secondary.http-address 127.0.0.1:19868
  prop dfs.datanode.address 127.0.0.1:19866; prop dfs.datanode.http.address 127.0.0.1:19864
  prop dfs.datanode.ipc.address 127.0.0.1:19867
  echo '</configuration>'; } > "$CR/conf/hdfs-site.xml"
cp "$CR/conf/hdfs-site.xml" "$L/hdfs-site.xml"; cp "$CR/conf/core-site.xml" "$L/core-site.xml"
run hdfs namenode -format -force -nonInteractive > "$L/format.log" 2>&1 || exit 1
run hdfs --daemon start namenode || exit 1
run hdfs --daemon start datanode || exit 1
for i in $(seq 1 60); do hdfs dfsadmin -report 2>/dev/null | grep -q '^Live datanodes (1)' && break; sleep 2; done
run hdfs dfsadmin -safemode wait
sleep 4
dnvol() { curl -s "$DNJMX?qry=Hadoop:service=DataNode,name=DataNodeInfo" | python3 -I -c '
import sys,json
v=json.loads(json.load(sys.stdin)["beans"][0]["VolumeInfo"])
for k in sorted(v): d=v[k]; print("VOL",k,d.get("storageType"),"used=%s free=%s reserved=%s rfr=%s blocks=%s"%(d.get("usedSpace"),d.get("freeSpace"),d.get("reservedSpace"),d.get("reservedSpaceForReplicas"),d.get("numBlocks")))'; }
archfree() { curl -s "$DNJMX?qry=Hadoop:service=DataNode,name=DataNodeInfo" | python3 -I -c '
import sys,json
v=json.loads(json.load(sys.stdin)["beans"][0]["VolumeInfo"])
a=[d for k,d in v.items() if "archive" in k][0]; print("%s,%s"%(a.get("freeSpace"),a.get("usedSpace")))'; }
dnact() { curl -s "$DNJMX?qry=Hadoop:service=DataNode,name=DataNodeActivity-*" | python3 -I -c '
import sys,json
b=json.load(sys.stdin)["beans"][0]; print("ACT ReplaceBlockOpOnSameMount=%s ReplaceBlockOpOnSameHost=%s ReplaceBlockOpToOtherHost=%s ReplaceBlockOpNumOps=%s"%(b.get("ReplaceBlockOpOnSameMount"),b.get("ReplaceBlockOpOnSameHost"),b.get("ReplaceBlockOpToOtherHost"),b.get("ReplaceBlockOpNumOps")))'; }
nnstats() { curl -s "$NNJMX?qry=Hadoop:service=NameNode,name=BlockStats" | python3 -I -c '
import sys,json
b=json.load(sys.stdin)["beans"][0]
for e in b.get("StorageTypeStats",[]): print("NNSTAT",e["key"],"capacityTotal=%s capacityUsed=%s capacityRemaining=%s nodesInService=%s"%(e["value"].get("capacityTotal"),e["value"].get("capacityUsed"),e["value"].get("capacityRemaining"),e["value"].get("nodesInService")))'; }
fsum() { find "$1/current" -type f -name 'blk_*' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{print s+0}'; }
fcnt() { find "$1/current" -type f -name 'blk_*' ! -name '*.meta' 2>/dev/null | wc -l; }
state() { echo "STATE $1 archBytes=$(fsum $MNT/dn/archive) archBlocks=$(fcnt $MNT/dn/archive) diskBytes=$(fsum $MNT/dn/disk) diskBlocks=$(fcnt $MNT/dn/disk) dfUsed=$(df -B1 --output=used $MNT | tail -1)"; dnvol; dnact; nnstats; }
echo "--- START check"
run hdfs dfsadmin -report > "$L/report-start.txt" 2>&1; grep -E '^(Configured Capacity|DFS Remaining|DFS Used):' "$L/report-start.txt" | head -3
grep -iE 'Added volume|same.?disk|reserve-for-archive|Adding block pool' "$L"/hadoop-*-datanode-*.log | head -10
state start
# data (B3e step 4)
run hdfs dfs -mkdir /cold
for i in $(seq -w 1 32); do hdfs dfs -put "$CR/blk.bin" /cold/f$i || echo "PUT FAILED f$i"; done
sleep 3
run hdfs fsck /cold -files -blocks -locations > "$L/fsck-before.txt" 2>&1
echo "fsck DISK replicas: $(grep -o 'DatanodeInfoWithStorage\[[^]]*\]' "$L/fsck-before.txt" | grep -c DISK)  ARCHIVE: $(grep -o 'DatanodeInfoWithStorage\[[^]]*\]' "$L/fsck-before.txt" | grep -c ARCHIVE)"
state before-mover
run hdfs storagepolicies -setStoragePolicy -path /cold -policy COLD
# sampler (B3d)
( echo "ts,archFree,archUsed,archBytes,archBlocks,diskBytes,dfUsed" > "$L/samples.csv"
  while true; do echo "$(date +%s),$(archfree 2>/dev/null),$(fsum $MNT/dn/archive),$(fcnt $MNT/dn/archive),$(fsum $MNT/dn/disk),$(df -B1 --output=used $MNT | tail -1)" >> "$L/samples.csv"; sleep 2; done ) &
SAMPLER=$!; echo "sampler pid $SAMPLER"
MOVD="-D dfs.heartbeat.interval=1 -D dfs.namenode.redundancy.interval.seconds=1"
[ -n "$CONC" ] && MOVD="-D dfs.datanode.balance.max.concurrent.moves=$CONC $MOVD"
echo "+ hdfs mover $MOVD -p /cold  [$(date '+%F %T %Z')]"
timeout 1200 hdfs mover $MOVD -p /cold > "$L/mover.log" 2>&1; MRC=$?
echo "mover exit=$MRC  [$(date '+%F %T %Z')]"; tail -3 "$L/mover.log"
sleep 10
kill "$SAMPLER" 2>/dev/null; SAMPLER=
state after-mover
echo "links>1 in archive: $(find $MNT/dn/archive/current -name 'blk_*' -type f -links +1 | wc -l)"
run hdfs fsck /cold -files -blocks -locations > "$L/fsck-after.txt" 2>&1
echo "fsck DISK replicas: $(grep -o 'DatanodeInfoWithStorage\[[^]]*\]' "$L/fsck-after.txt" | grep -c DISK)  ARCHIVE: $(grep -o 'DatanodeInfoWithStorage\[[^]]*\]' "$L/fsck-after.txt" | grep -c ARCHIVE)"
DNLOG=$(ls "$L"/hadoop-*-datanode-*.log | head -1)
echo "DN Moved-to-ARCHIVE lines: $(grep -c 'from StorageType DISK to ARCHIVE' "$DNLOG")"
echo "DN distinct blocks moved: $(grep 'from StorageType DISK to ARCHIVE' "$DNLOG" | grep -o 'blk_[0-9]*' | sort -u | wc -l)"
echo "DN 'Out of space' lines: $(grep -c 'Out of space' "$DNLOG")"
echo "DN distinct blocks refused: $(grep 'opReplaceBlock.*Out of space' "$DNLOG" | grep -o 'blk_[0-9]*' | sort -u | wc -l)"
echo "DN fallback WARN lines (archive): $(grep 'is less than the block size' "$DNLOG" | grep -c archive)"
echo "DN fallback WARN available values (archive), distinct:"; grep 'is less than the block size' "$DNLOG" | grep archive | grep -o 'available space (=[0-9]* B)' | sort | uniq -c
grep -E 'from StorageType DISK to ARCHIVE|opReplaceBlock|is less than the block size' "$DNLOG" > "$L/dn-move-lines.txt"
echo "RESULT $CFG r=$R_ tiering=$TIER conc=${CONC:-default} archBlocks=$(fcnt $MNT/dn/archive) archBytes=$(fsum $MNT/dn/archive) diskBlocks=$(fcnt $MNT/dn/disk) moverExit=$MRC"
run df -B1 "$MNT"
trap - EXIT; stopall
echo "=== cluster-run.sh $CFG end $(date '+%F %T %Z')"
