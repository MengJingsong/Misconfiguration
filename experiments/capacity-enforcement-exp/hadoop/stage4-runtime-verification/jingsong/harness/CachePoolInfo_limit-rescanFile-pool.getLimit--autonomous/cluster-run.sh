#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + A4-A8) for CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous. Runs on pc75.
# Usage: cluster-run.sh <harness-dir> setup|run|stop
#   setup: native hadoop-common build in the case copy, dist copy, configs, checknative
#   run:   format, start NN+DN, workload and all phases (B3e steps 2-7), then stop daemons
#   stop:  stop daemons (idempotent)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=CachePoolInfo_limit-rescanFile-pool.getLimit--autonomous
RUNDIR=/mydata/jingsong-s4/$STEM-run1
SRC=$RUNDIR/src
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
U=1048576
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pid
export HADOOP_HEAPSIZE_MAX=1g
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
die() { echo "STOP: $*"; exit 1; }
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"

jmxcache() { curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=FSDatasetState*' \
  | python3 -I -c 'import json,sys; b=json.load(sys.stdin)["beans"][0]; print(b["CacheUsed"], b["NumBlocksCached"], b["CacheCapacity"])'; }
dnpid() { cat "$HADOOP_PID_DIR/hadoop-$USER-datanode.pid"; }
vmlck() { awk '/^VmLck/{print $2}' "/proc/$(dnpid)/status"; }
nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
waitzero() {  # wait until DN CacheUsed = 0 (max 90 s)
  for i in $(seq 1 45); do set -- $(jmxcache); [ "${1:-x}" = 0 ] && { echo "  CacheUsed=0 after $((i*2)) s; VmLck=$(vmlck) kB"; return 0; }; sleep 2; done
  echo "  CacheUsed not 0 after 90 s: $(jmxcache)"; return 1; }
waitdn() {  # wait for 1 live DN with cache capacity reported
  for i in $(seq 1 60); do
    n=$(hdfs dfsadmin -report 2>/dev/null | grep -oE 'Live datanodes \([0-9]+\)' | grep -oE '[0-9]+')   # fixed (defect D-2)
    [ "${n:-0}" = 1 ] && { hdfs dfsadmin -report | grep -E 'Live datanodes|Cache Capacity|Cache Used' | head -4; return 0; }; sleep 2; done
  return 1; }
stash_out() { hdfs dfs -mkdir -p /stash; for i in 01 02 03 04 05 06; do hdfs dfs -test -e /d/f$i && hdfs dfs -mv /d/f$i /stash/; done; hdfs dfs -ls /d /stash; }
stash_in()  { for i in 01 02 03 04 05 06; do hdfs dfs -mv /stash/f$i /d/; done; }
# phase <name> <pool> <limit-arg> : pool + directive on the EMPTY /d (A8), then files moved in, then sample
phase() {
  local name=$1 pool=$2 lim=$3
  echo "--- phase $name: pool $pool limit $lim"
  stash_out
  run hdfs cacheadmin -addPool "$pool" -limit "$lim" || die "addPool"
  run hdfs cacheadmin -addDirective -path /d -pool "$pool" -replication 1 || die "addDirective (empty /d)"
  local off; off=$(stat -c %s "$(nnlog)")
  stash_in
  local t0; t0=$(date +%s.%N)
  run python3 -I "$H/sampler.py" "$name" "$pool" "$lim" "$t0" "$(nnlog)" "$off" "$(dnpid)" "$VBASE" "$LOGS/samples-$name.csv"
  run hdfs cacheadmin -listDirectives -stats -pool "$pool"
  hdfs dfsadmin -report | grep -E 'Cache (Capacity|Used)' | head -2
}
endphase() {  # remove directives and pool, wait for an empty cache
  run hdfs cacheadmin -removeDirectives -path /d
  run hdfs cacheadmin -removePool "$1"
  waitzero
}
stopall() {
  hdfs --daemon stop datanode; hdfs --daemon stop namenode; sleep 3
  echo "+ ps check:"; ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode|[N]ameNode|[D]ataNode' | grep "$RUN" | cut -c1-120 || echo "  no NameNode/DataNode of this run"
}

case "$MODE" in
setup)
  [ -x "$DIST/bin/hadoop" ] || die "no base dist"
  [ -d "$SRC" ] || die "no source copy (unit-run.sh makes it)"
  cd "$SRC" || exit 1
  run mvn -B -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests -Dmaven.javadoc.skip=true \
    > "$LOGS/native-build.log" 2>&1
  grep -E "BUILD (SUCCESS|FAILURE)|Total time" "$LOGS/native-build.log"
  NL=$SRC/hadoop-common-project/hadoop-common/target/native/target/usr/local/lib
  run ls -l "$NL" || die "no native lib"
  rm -rf "$RUN"; mkdir -p "$RUN"/{logs,pid,tmp}
  run cp -a "$DIST" "$RUN/hadoop" || die "dist copy"
  run mkdir -p "$RUN/hadoop/lib/native"   # the non-native dist has no lib/native (defect D-1)
  run cp -a "$NL"/libhadoop.so* "$RUN/hadoop/lib/native/" || die "copy native"
  run cp -r "$RUN/hadoop/etc/hadoop" "$RUN/conf"
  cat > "$RUN/conf/core-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:8020</value></property>
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
  <property><name>dfs.datanode.max.locked.memory</name><value>8388608</value></property>
  <property><name>dfs.namenode.path.based.cache.refresh.interval.ms</name><value>2000</value></property>
  <property><name>dfs.cachereport.intervalMsec</name><value>2000</value></property>
  <property><name>dfs.heartbeat.interval</name><value>1</value></property>
</configuration>
EOF
  run cat "$RUN/conf/core-site.xml" "$RUN/conf/hdfs-site.xml"
  run hadoop version | head -1
  run hadoop checknative
  echo "+ ulimit -l: $(ulimit -l)"
  ;;
run)
  echo "+ ulimit -l: $(ulimit -l)"
  hadoop checknative 2>&1 | grep -E '^hadoop:' | grep -q true || die "native hadoop not true"
  echo "+ ss -ltn on 8020 9870 9864 9866 9867:"; busy=$(ss -ltn | grep -E ':(8020|9870|9864|9866|9867) '); echo "${busy:-  free}"
  [ -z "$busy" ] || die "ports busy"
  jps
  # fresh state for every attempt (defect D-2: an aborted attempt leaves nn/dn data and daemon logs)
  if [ -d "$RUN/nn" ] || [ -n "$(ls -A "$RUN/logs" 2>/dev/null)" ]; then
    a="$LOGS/aborted-$(date +%H%M%S)"; mkdir -p "$a"; cp -a "$RUN/logs/." "$a/" 2>/dev/null
    echo "+ previous attempt: daemon logs kept in $a; removing nn dn tmp logs pid"
    rm -rf "$RUN/nn" "$RUN/dn" "$RUN"/tmp/* "$RUN"/logs/* "$RUN"/pid/* "$RUN"/f0?
  fi
  run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die "format"
  run hdfs --daemon start namenode || die "nn"
  run hdfs --daemon start datanode || die "dn"
  waitdn || { stopall; die "DN not live"; }
  run hdfs dfsadmin -safemode wait
  run hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor DEBUG
  echo "+ DN pid $(dnpid); jmx: $(jmxcache)"
  grep -E 'maxLockedMemory|NativeCodeLoader' "$HADOOP_LOG_DIR"/hadoop-$USER-datanode-*.log | head -3
  sleep 4; VBASE=$(vmlck); echo "VmLck baseline (kB) = $VBASE"
  # B3c workload: six files of exactly 1 MiB (put into /stash; phase() moves them into /d after the directive)
  run hdfs dfs -mkdir -p /d /stash
  for i in 01 02 03 04 05 06; do head -c $U /dev/urandom > "$RUN/f$i"; hdfs dfs -D dfs.blocksize=$U -put "$RUN/f$i" /stash/f$i; done
  run hdfs fsck /stash -files -blocks | grep -E 'bytes|blk_' | head -12
  # step 4: knob values (unlimited first)
  for spec in unlimited:unlimited L0:0 L2U:2097152 L2.5U:2621440 L4U:4194304; do
    nm=${spec%%:*}; lim=${spec#*:}
    phase "$nm" p "$lim"; endphase p
  done
  # step 5: live lowering
  phase lowering-before p unlimited
  off=$(stat -c %s "$(nnlog)"); t0=$(date +%s.%N)
  run hdfs cacheadmin -modifyPool p -limit 3145728
  run python3 -I "$H/sampler.py" lowering-after p 3145728 "$t0" "$(nnlog)" "$off" "$(dnpid)" "$VBASE" "$LOGS/samples-lowering-after.csv"
  run hdfs cacheadmin -listDirectives -stats -pool p
  endphase p   # A5
  # step 6: add-time contrast on the populated /d, pool r only
  stash_out; stash_in
  run hdfs cacheadmin -addPool r -limit 2097152
  run hdfs cacheadmin -addDirective -path /d -pool r -replication 1; echo "  (expected: add-time limit error)"
  run hdfs cacheadmin -listDirectives -pool r
  off=$(stat -c %s "$(nnlog)"); t0=$(date +%s.%N)
  run hdfs cacheadmin -addDirective -path /d -pool r -replication 1 -force
  run python3 -I "$H/sampler.py" force r 2097152 "$t0" "$(nnlog)" "$off" "$(dnpid)" "$VBASE" "$LOGS/samples-force.csv"
  run hdfs cacheadmin -listDirectives -stats -pool r
  endphase r   # A5
  # step 7: DN-cap control
  run sed -i 's#<value>8388608</value>#<value>3145728</value>#' "$RUN/conf/hdfs-site.xml"
  grep max.locked "$RUN/conf/hdfs-site.xml"
  run hdfs --daemon stop datanode; sleep 3
  run hdfs --daemon start datanode
  waitdn || { stopall; die "DN not live after restart"; }
  sleep 4; VBASE=$(vmlck); echo "VmLck baseline after DN restart (kB) = $VBASE; jmx: $(jmxcache)"
  phase dncap p unlimited; endphase p
  # cleanup of HDFS objects and daemons (B4)
  run hdfs cacheadmin -listPools
  stopall
  echo "=== cluster-run.sh run end $(date '+%F %T %Z')"
  ;;
stop) stopall ;;
esac
