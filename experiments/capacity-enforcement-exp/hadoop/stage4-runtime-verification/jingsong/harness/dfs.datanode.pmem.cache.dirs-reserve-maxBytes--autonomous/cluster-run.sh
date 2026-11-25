#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + S4-S6) for dfs.datanode.pmem.cache.dirs-reserve-maxBytes--autonomous. Runs on pc82.
# Usage: cluster-run.sh setup|run|stop
#   setup: base distribution copy, configuration (no build; no libhadoop -> pure-Java pmem loader)
#   run:   format, NN, put /f (20 x 32 MiB), then runs A0 (128m), A (256m), B (512m), C (two dirs on 256m), D (unset):
#          remount tmpfs, DN start, directive, 90 s of 2-s samples, directive removed, wait for 0, DN stop, unmount
#   stop:  stop daemons and unmount (idempotent)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
MODE=${1:?mode}
RUNDIR=/mydata/jingsong-s4/dfs.datanode.pmem.cache.dirs-reserve-maxBytes-run1
H=$RUNDIR/harness
CL=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
PM=$CL/pmem0
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
BS=33554432
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$CL/hadoop HADOOP_CONF_DIR=$CL/conf HADOOP_LOG_DIR=$CL/logs HADOOP_PID_DIR=$CL/pid
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T %Z')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"

nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
jmx() { curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*' | python3 -I -c '
import json,sys
bs=json.load(sys.stdin)["beans"]; b=([x for x in bs if "FSDatasetState-" in x["name"]] or bs)[0]
print(b["CacheCapacity"], b["CacheUsed"], b["NumBlocksCached"], b["NumBlocksFailedToCache"])' 2>/dev/null; }
filebytes() { [ -d "$PM" ] && find "$PM" -type f -printf '%s\n' | awk '{s+=$1} END{print s+0, NR}' || echo "0 0"; }
umountpm() { if mountpoint -q "$PM"; then run sudo umount "$PM"; fi; mountpoint -q "$PM" && echo "  WARN: $PM still mounted"; true; }
mountpm() {  # $1 = size
  umountpm; mkdir -p "$PM"
  run sudo mount -t tmpfs -o "size=$1,uid=$(id -u),gid=$(id -g),mode=0755" tmpfs "$PM" || return 1
  run df -B1 "$PM"; }
writesite() {  # $1 = pmem dirs value or "" (property left out)
  local p=""
  [ -n "$1" ] && p="  <property><name>dfs.datanode.pmem.cache.dirs</name><value>$1</value></property>"
  cat > "$CL/conf/hdfs-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>$CL/nn</value></property>
  <property><name>dfs.datanode.data.dir</name><value>$CL/dn</value></property>
  <property><name>dfs.blocksize</name><value>$BS</value></property>
$p
  <property><name>dfs.datanode.pmem.cache.recovery</name><value>false</value></property>
  <property><name>dfs.namenode.path.based.cache.refresh.interval.ms</name><value>3000</value></property>
  <property><name>dfs.cachereport.intervalMsec</name><value>3000</value></property>
  <property><name>dfs.datanode.max.locked.memory</name><value>0</value></property>
</configuration>
EOF
  grep -E 'pmem|locked' "$CL/conf/hdfs-site.xml"; }
startdn() {  # wait until DN JMX answers and the NN reports the same cache capacity
  run hdfs --daemon start datanode || return 1
  local c
  for i in $(seq 1 60); do
    set -- $(jmx)
    if [ -n "${1:-}" ]; then
      c=$1
      r=$(hdfs dfsadmin -report 2>/dev/null)
      if echo "$r" | grep -q "Live datanodes (1)" && echo "$r" | grep -qE "^Configured Cache Capacity: $c "; then
        echo "  DN live after ~$((i*2)) s; jmx: $(jmx)"
        echo "$r" | grep -E 'Live datanodes|Cache Capacity|Cache Used|Cache Remaining' | head -5; return 0; fi
    fi; sleep 2; done
  echo "  DN not live with matching capacity in 120 s; jmx: $(jmx)"; return 1; }
stopdn() {
  run hdfs --daemon stop datanode; sleep 3
  ps -u "$(id -un)" -o pid=,args= | awk -v r="$CL" '/proc_datanode/ && index($0, r) && !/awk/' | grep -q . \
    && echo "  WARN: DataNode still running" || echo "  DataNode of this run stopped"; }
stopall() {
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; sleep 3
  echo "+ ps check:"; ps -u "$(id -un)" -o pid=,args= | awk -v r="$CL" '(/proc_namenode/ || /proc_datanode/) && index($0, r) && !/awk/' \
    | cut -c1-150 | grep . || echo "  no NameNode/DataNode of this run"
  umountpm; }
die() { echo "STOP: $*"; stopall; exit 1; }

# phase <name> <tmpfs size or -> <dirs: one|two|none>
phase() {
  local name=$1 size=$2 mode=$3 dirs=""
  echo "--- run $name: tmpfs=$size dirs=$mode  [$(date '+%F %T %Z') / $(date -u '+%T UTC')]"
  if [ "$size" != "-" ]; then mountpm "$size" || die "mount"; fi
  case $mode in
    one) dirs=$PM ;;
    two) run mkdir -p "$PM/a" "$PM/b"; dirs="$PM/a,$PM/b" ;;
    none) umountpm; dirs="" ;;
  esac
  writesite "$dirs"
  local nno dno; nno=$(stat -c %s "$(nnlog)"); dno=$(stat -c %s "$(dnlog)" 2>/dev/null || echo 0)
  startdn || die "dn start ($name)"
  echo "+ DN log (this start):"
  tail -c +$((dno+1)) "$(dnlog)" | grep -E 'Starting DataNode with maxLockedMemory|Initializing cache loader|Added persistent memory|Persistent memory is used|Bad persistent memory|Failed to parse' | cut -c1-260
  [ "$size" != "-" ] && run df -B1 "$PM"
  echo "+ cache files before directive: $(filebytes) (bytes files)"
  nno=$(stat -c %s "$(nnlog)"); dno=$(stat -c %s "$(dnlog)")
  run hdfs cacheadmin -addDirective -path /f -pool p1 -replication 1 || die "addDirective"
  run python3 -I "$H/sampler.py" "$name" "$( [ "$size" != "-" ] && echo "$PM" || echo - )" 90 "$(nnlog)" "$nno" "$(dnlog)" "$dno" "$LOGS/samples-$name.csv"
  run hdfs cacheadmin -listDirectives -stats -path /f
  hdfs dfsadmin -report | grep -E 'Configured Cache Capacity|Cache Used|Cache Remaining' | head -3
  [ "$size" != "-" ] && { run df -B1 "$PM"; echo "+ cache files: $(filebytes) (bytes files)"; find "$PM" -type f -printf '%s %p\n' | sort -k2 | sed "s#$PM#<pmem0>#" ; }
  echo "+ DN log lines for this run (counts):"
  for p in 'could not reserve more bytes' 'There is no enough persistent memory space' 'Failed to cache the block' \
           'No space left on device' 'premature EOF' 'checksum verification failed' 'Successfully cached one replica'; do
    echo "  dn \"$p\": $(tail -c +$((dno+1)) "$(dnlog)" | grep -c "$p")"; done
  for p in 'is not a valid possibility because the block has size' 'added to PENDING_CACHED on DataNode'; do
    echo "  nn \"$p\": $(tail -c +$((nno+1)) "$(nnlog)" | grep -c "$p")"; done
  tail -c +$((dno+1)) "$(dnlog)" > "$LOGS/dn-$name.log"
  tail -c +$((nno+1)) "$(nnlog)" | grep -E 'is not a valid possibility|added to PENDING_CACHED' > "$LOGS/nn-gate-$name.log"
  run hdfs cacheadmin -removeDirectives -path /f
  local ok=0
  for i in $(seq 1 60); do
    set -- $(jmx); fb=$(filebytes)
    if [ "${2:-x}" = 0 ] && [ "${fb#* }" = 0 ]; then echo "  CacheUsed=0 and no cache file after $((i*2)) s; jmx: $*"; ok=1; break; fi
    sleep 2; done
  [ $ok = 1 ] || echo "  NOT drained in 120 s: jmx $(jmx); files $(filebytes)"
  stopdn
  [ "$size" != "-" ] && umountpm
  true; }

case "$MODE" in
setup)
  [ -x "$DIST/bin/hadoop" ] || { echo "STOP: no base dist"; exit 1; }
  rm -rf "$CL"; mkdir -p "$CL"/{logs,pid,tmp,data}
  run cp -a "$DIST" "$CL/hadoop" || exit 1
  run cp -r "$CL/hadoop/etc/hadoop" "$CL/conf"
  echo 'log4j.logger.org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor=TRACE' >> "$CL/conf/log4j.properties"
  cat > "$CL/conf/core-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:9000</value></property>
  <property><name>hadoop.tmp.dir</name><value>$CL/tmp</value></property>
</configuration>
EOF
  writesite ""
  run tail -1 "$CL/conf/log4j.properties"
  run cat "$CL/conf/core-site.xml"
  run hadoop version | head -1
  run ls "$CL/hadoop/lib/native"
  run hadoop checknative
  ;;
run)
  busy=$(ss -ltn | grep -E ':(9000|9870|9864|9866|9867|9868) '); echo "+ ports 9000 9870 9864 9866 9867 9868: ${busy:-free}"
  [ -z "$busy" ] || { echo "STOP: ports busy"; exit 1; }
  mountpoint -q "$PM" && { echo "STOP: $PM already mounted"; exit 1; }
  run free -m
  run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die "format"
  run hdfs --daemon start namenode || die "nn"
  writesite ""
  startdn || die "dn (put)"
  run hdfs dfsadmin -safemode wait
  run head -c 671088640 /dev/urandom > "$CL/data/in.bin"
  run ls -l "$CL/data/in.bin"
  run hdfs dfs -put "$CL/data/in.bin" /f || die "put"
  echo "+ blocks of /f: $(hdfs fsck /f -files -blocks 2>/dev/null | grep -cE 'blk_[0-9]+_[0-9]+ len=33554432')"
  run hdfs cacheadmin -addPool p1
  run hdfs cacheadmin -listPools
  stopdn
  phase A0 128m one
  phase A 256m one
  phase B 512m one
  phase C 256m two
  phase D - none
  run hdfs cacheadmin -removePool p1
  stopall
  run free -m
  ;;
stop)
  stopall ;;
esac
echo "=== cluster-run.sh $MODE end $(date '+%F %T %Z')"
