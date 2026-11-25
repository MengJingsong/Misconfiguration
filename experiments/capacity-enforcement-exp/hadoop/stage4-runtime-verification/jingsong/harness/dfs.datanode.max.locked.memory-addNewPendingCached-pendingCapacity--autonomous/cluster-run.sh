#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + A4-A7) for dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous.
# Runs on pc82. Usage: cluster-run.sh <harness-dir> setup|run|stop
#   setup: native hadoop-common build in the case copy, dist copy + libhadoop, configs, checknative
#   run:   format, NN, then per C: DN start, directive, sample, remove, DN stop (B3e 2-9), then stop all
#   stop:  stop daemons (idempotent)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.datanode.max.locked.memory-addNewPendingCached-pendingCapacity--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
MiB=1048576
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pid
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
die() { echo "STOP: $*"; stopall; exit 1; }
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"

jmx() { curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*' \
  | python3 -I -c 'import json,sys; b=json.load(sys.stdin)["beans"][0]; print(b["CacheCapacity"], b["CacheUsed"], b["NumBlocksCached"], b["NumBlocksFailedToCache"])' 2>/dev/null; }
dnpid() { cat "$HADOOP_PID_DIR/hadoop-$USER-datanode.pid"; }
vmlck() { awk '/^VmLck/{print $2}' "/proc/$(dnpid)/status"; }
nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
waitzero() {  # wait until DN CacheUsed = 0 (max 120 s)
  for i in $(seq 1 60); do set -- $(jmx); [ "${2:-x}" = 0 ] && { echo "  CacheUsed=0 after $((i*2)) s; VmLck=$(vmlck) kB; jmx: $*"; return 0; }; sleep 2; done
  echo "  CacheUsed not 0 after 120 s: $(jmx)"; return 1; }
waitdn() {  # $1 = C: wait until the DN's JMX and the NN report both show cache capacity C
  for i in $(seq 1 60); do
    set -- "$1" $(jmx)
    if [ "${2:-x}" = "$1" ]; then
      r=$(hdfs dfsadmin -report 2>/dev/null)
      if echo "$r" | grep -qE "^Configured Cache Capacity: $1 "; then
        echo "$r" | grep -E 'Live datanodes|Cache Capacity|Cache Used|Cache Remaining' | head -6; return 0; fi
    fi; sleep 2; done
  return 1; }
setC() { run sed -i "s#<name>dfs.datanode.max.locked.memory</name><value>[0-9]*</value>#<name>dfs.datanode.max.locked.memory</name><value>$1</value>#" "$RUN/conf/hdfs-site.xml"; grep max.locked "$RUN/conf/hdfs-site.xml"; }
stopdn() {
  run hdfs --daemon stop datanode; sleep 3
  ps -eo pid,cmd | grep -E '[p]roc_datanode' | grep -q "$RUN" && echo "  WARN: DataNode still running" || echo "  DataNode of this run stopped"; }
stopall() {
  hdfs --daemon stop datanode 2>/dev/null; hdfs --daemon stop namenode 2>/dev/null; sleep 3
  echo "+ ps check:"; ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode' | grep "$RUN" | cut -c1-120 || echo "  no NameNode/DataNode of this run"; }
# phase <name> <C> <path>: DN with cap C, directive on <path>, sample (A5), directive removed, DN stopped
phase() {
  local name=$1 C=$2 path=$3
  echo "--- phase $name: C=$C path=$path"
  setC "$C"
  run hdfs --daemon start datanode || die "dn start"
  waitdn "$C" || die "DN not live with capacity $C"
  echo "+ DN log: $(grep 'Starting DataNode with maxLockedMemory' "$(dnlog)" | tail -1)"
  sleep 4; VBASE=$(vmlck); echo "VmLck baseline (kB) = $VBASE; DN pid $(dnpid); jmx: $(jmx)"
  local nno dno t0; nno=$(stat -c %s "$(nnlog)"); dno=$(stat -c %s "$(dnlog)"); t0=$(date +%s.%N)
  run hdfs cacheadmin -addDirective -path "$path" -pool p -replication 1 || die "addDirective"
  run python3 -I "$H/sampler.py" "$name" "$C" "$path" "$t0" "$(nnlog)" "$nno" "$(dnlog)" "$dno" "$(dnpid)" "$VBASE" "$LOGS/samples-$name.csv"
  run hdfs cacheadmin -listDirectives -stats -path "$path"
  hdfs dfsadmin -report | grep -E 'Cache (Capacity|Used|Remaining)' | head -3
  echo "+ VmLck line: $(grep VmLck /proc/$(dnpid)/status)"
  run hdfs cacheadmin -removeDirectives -path "$path"
  waitzero
  echo "VmLck after removal (kB) = $(vmlck) (baseline $VBASE)"
  stopdn
}

case "$MODE" in
setup)
  [ -x "$DIST/bin/hadoop" ] || { echo "STOP: no base dist"; exit 1; }
  [ -d "$SRC" ] || { echo "STOP: no source copy"; exit 1; }
  run cmake --version | head -1
  cd "$SRC" || exit 1
  run mvn -B -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests -Dmaven.javadoc.skip=true \
    > "$LOGS/native-build.log" 2>&1
  grep -E "BUILD (SUCCESS|FAILURE)|Total time" "$LOGS/native-build.log"
  NL=$SRC/hadoop-common-project/hadoop-common/target/native/target/usr/local/lib
  run ls -l "$NL" || { echo "STOP: no native lib"; exit 1; }
  rm -rf "$RUN"; mkdir -p "$RUN"/{logs,pid,tmp,data}
  run cp -a "$DIST" "$RUN/hadoop" || exit 1
  run mkdir -p "$RUN/hadoop/lib/native"
  run cp -a "$NL"/libhadoop.so* "$RUN/hadoop/lib/native/" || exit 1
  run cp -r "$RUN/hadoop/etc/hadoop" "$RUN/conf"
  cat > "$RUN/conf/core-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:9000</value></property>
  <property><name>hadoop.tmp.dir</name><value>$RUN/tmp</value></property>
</configuration>
EOF
  cat > "$RUN/conf/hdfs-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>$RUN/nn</value></property>
  <property><name>dfs.datanode.data.dir</name><value>$RUN/dn</value></property>
  <property><name>dfs.blocksize</name><value>1048576</value></property>
  <property><name>dfs.datanode.max.locked.memory</name><value>0</value></property>
  <property><name>dfs.namenode.path.based.cache.refresh.interval.ms</name><value>3000</value></property>
  <property><name>dfs.cachereport.intervalMsec</name><value>3000</value></property>
</configuration>
EOF
  run cat "$RUN/conf/core-site.xml" "$RUN/conf/hdfs-site.xml"
  run hadoop version | head -1
  run hadoop checknative
  echo "+ ulimit -H -l: $(ulimit -H -l); ulimit -S -l: $(ulimit -S -l)"
  ;;
run)
  echo "+ ulimit -H -l: $(ulimit -H -l); ulimit -S -l: $(ulimit -S -l)"
  hadoop checknative 2>&1 | grep -E '^hadoop:' | grep -q true || { echo "STOP: native hadoop not true"; exit 1; }
  busy=$(ss -ltn | grep -E ':(9000|9870|9864|9866|9867) '); echo "+ ports 9000 9870 9864 9866 9867: ${busy:-free}"
  [ -z "$busy" ] || { echo "STOP: ports busy"; exit 1; }
  if [ -d "$RUN/nn" ] || [ -n "$(ls -A "$RUN/logs" 2>/dev/null)" ]; then
    a="$LOGS/aborted-$(date +%H%M%S)"; mkdir -p "$a"; cp -a "$RUN/logs/." "$a/" 2>/dev/null
    echo "+ previous attempt: daemon logs kept in $a; removing nn dn tmp logs pid data"
    rm -rf "$RUN/nn" "$RUN/dn" "$RUN"/tmp/* "$RUN"/logs/* "$RUN"/pid/* "$RUN"/data/*
  fi
  run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die "format"
  run hdfs --daemon start namenode || die "nn"
  # B3e step 3-5, C = 0 first; the DN must be up to write /big
  setC 0
  run hdfs --daemon start datanode || die "dn"
  waitdn 0 || die "DN not live (C=0)"
  run hdfs dfsadmin -safemode wait
  run dd if=/dev/urandom of="$RUN/data/f16" bs=1M count=16
  run dd if=/dev/urandom of="$RUN/data/f4" bs=1M count=4
  run hdfs dfs -put "$RUN/data/f16" /big || die "put /big"
  run hdfs dfs -put "$RUN/data/f4" /small || die "put /small"
  run hdfs fsck /big -files -blocks | grep -cE 'blk_'
  run hdfs fsck /small -files -blocks | grep -cE 'blk_'
  run hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor TRACE
  run hdfs cacheadmin -addPool p
  stopdn
  # main series (B3b): C = 0, 2, 4, 6 MiB, then the /small control at 6 MiB (B3e step 8)
  phase C0 0 /big
  phase C2M $((2*MiB)) /big
  phase C4M $((4*MiB)) /big
  phase C6M $((6*MiB)) /big
  phase ctrl-small-C6M $((6*MiB)) /small
  # optional larger series (B3b, A6): 16-MiB blocks, 512-MiB file, C = 64, 128, 256 MiB
  setC 0
  run hdfs --daemon start datanode || die "dn"
  waitdn 0 || die "DN not live (C=0, large put)"
  run dd if=/dev/urandom of="$RUN/data/f512" bs=1M count=512
  run hdfs dfs -D dfs.blocksize=$((16*MiB)) -put "$RUN/data/f512" /big2 || die "put /big2"
  run hdfs fsck /big2 -files -blocks | grep -cE 'blk_'
  rm -f "$RUN/data/f512"
  stopdn
  phase L64M $((64*MiB)) /big2
  phase L128M $((128*MiB)) /big2
  phase L256M $((256*MiB)) /big2
  run hdfs cacheadmin -removePool p
  stopall
  echo "=== cluster-run.sh run end $(date '+%F %T %Z')"
  ;;
stop) stopall ;;
esac
