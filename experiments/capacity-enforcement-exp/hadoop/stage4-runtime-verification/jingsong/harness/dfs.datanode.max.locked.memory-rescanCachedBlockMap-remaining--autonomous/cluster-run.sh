#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + A5-A8) for dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.
# Runs on pc72 (2026-11-25 retry; first prepared for pc99). Usage: cluster-run.sh <harness-dir> deps|setup|run|phase2b|stop
#   deps:  apt install cmake zlib1g-dev libssl-dev pkg-config (A5; absent on pc72 as on pc99)
#   setup: native hadoop-common build in the case copy, dist copy, libhadoop, configs, checknative
#   run:   format, start NN+DN, workload, phase 1 (M = 0, 64m, 128m, 256m, 1g), phase 2 (M = 128m, cache report 60 s), cleanup
#   stop:  stop daemons (idempotent)
# Every command and its output is logged to $LOGS/cluster-run.log (append).
set -uo pipefail
H=${1:?harness dir}; MODE=${2:?mode}
STEM=dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous
RUNDIR=/mydata/jingsong-s4/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining-run1
SRC=$RUNDIR/src
RUN=$RUNDIR/cluster
LOGS=$RUNDIR/logs/cluster
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids
export HDFS_NAMENODE_OPTS="-Xmx1g" HDFS_DATANODE_OPTS="-Xmx1g"
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
mkdir -p "$LOGS"
exec > >(tee -a "$LOGS/cluster-run.log") 2>&1
run() { echo "+ $*  [$(date '+%F %T')]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
die() { echo "STOP: $*"; exit 1; }
echo "=== cluster-run.sh $MODE start $(date '+%F %T %Z') host=$(hostname)"

jmx() { curl -s "http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=$1*" \
  | python3 -I -c "import json,sys; b=json.load(sys.stdin)['beans'][0]; print(' '.join(str(b.get(k)) for k in sys.argv[1:]))" "${@:2}"; }
dnpid() { cat "$HADOOP_PID_DIR/hadoop-$USER-datanode.pid"; }
vmlck() { awk '/^VmLck/{print $2}' "/proc/$(dnpid)/status"; }
nnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-namenode-$(hostname).log"; }
dnlog() { echo "$HADOOP_LOG_DIR/hadoop-$USER-datanode-$(hostname).log"; }
setM() { sed -i "s#<name>dfs.datanode.max.locked.memory</name><value>[^<]*</value>#<name>dfs.datanode.max.locked.memory</name><value>$1</value>#" "$RUN/conf/hdfs-site.xml"; grep max.locked "$RUN/conf/hdfs-site.xml"; }
setCR() { sed -i "s#<name>dfs.cachereport.intervalMsec</name><value>[^<]*</value>#<name>dfs.cachereport.intervalMsec</name><value>$1</value>#" "$RUN/conf/hdfs-site.xml"; grep cachereport "$RUN/conf/hdfs-site.xml"; }
waitdn() {  # $1 = expected Configured Cache Capacity (bytes); 1 live DN reporting it
  for i in $(seq 1 60); do
    r=$(hdfs dfsadmin -report 2>/dev/null)
    n=$(echo "$r" | grep -oE 'Live datanodes \([0-9]+\)' | grep -oE '[0-9]+')
    c=$(echo "$r" | grep -oE 'Configured Cache Capacity: [0-9]+' | head -1 | grep -oE '[0-9]+$')
    [ "${n:-0}" = 1 ] && [ "${c:-x}" = "$1" ] && { echo "$r" | grep -E 'Live datanodes|Cache' | head -5; return 0; }
    sleep 2; done
  echo "$r" | head -40; return 1; }
waitzero() {  # DN CacheUsed = 0 and VmLck = baseline (max 120 s)
  for i in $(seq 1 60); do set -- $(jmx FSDatasetState CacheUsed NumBlocksCached)
    [ "${1:-x}" = 0 ] && [ "$(vmlck)" = "$VBASE" ] && { echo "  CacheUsed=0 blocks=$2 after $((i*2)) s; VmLck=$(vmlck) kB (baseline $VBASE)"; return 0; }; sleep 2; done
  echo "  not empty after 120 s: $(jmx FSDatasetState CacheUsed NumBlocksCached) VmLck=$(vmlck)"; return 1; }
stopall() {
  hdfs --daemon stop datanode; hdfs --daemon stop namenode; sleep 3
  echo "+ ps check:"; ps -eo pid,cmd | grep -E '[p]roc_namenode|[p]roc_datanode|[N]ameNode|[D]ataNode' | grep "$RUN" | cut -c1-160 || echo "  no NameNode/DataNode of this run"
}
restart_dn() {  # $1 = M value string, $2 = M bytes
  run hdfs --daemon stop datanode; sleep 3
  ps -eo pid,cmd | grep '[p]roc_datanode' | grep -q "$RUN" && die "DN still running"
  setM "$1"
  run hdfs --daemon start datanode || die "dn start"
  waitdn "$2" || { stopall; die "DN not live with capacity $2"; }
  grep -E 'Starting DataNode with maxLockedMemory' "$(dnlog)" | tail -1
}
# phase1 <name> <M bytes>: directive on /cap/f512, sample to plateau, remove directive, wait empty
phase1() {
  local name=$1 mb=$2
  echo "--- phase 1, $name (M = $mb)"
  sleep 4; VBASE=$(vmlck); echo "VmLck baseline (kB) = $VBASE; jmx: $(jmx FSDatasetState CacheUsed CacheCapacity NumBlocksCached NumBlocksFailedToCache)"
  local no dno t0; no=$(stat -c %s "$(nnlog)"); dno=$(stat -c %s "$(dnlog)"); t0=$(date +%s.%N)
  run hdfs cacheadmin -addDirective -path /cap/f512 -pool p -replication 1 || die "addDirective"
  run python3 -I "$H/sampler.py" "$name" "$mb" "$t0" "$(dnpid)" "$VBASE" "$(nnlog)" "$no" "$(dnlog)" "$dno" \
    "$LOGS/samples-$name.csv" plateau
  run hdfs cacheadmin -listDirectives -stats -path /cap/f512
  hdfs dfsadmin -report | grep -E 'Cache' | head -4
  run hdfs cacheadmin -removeDirectives -path /cap/f512
  waitzero
}

case "$MODE" in
deps)
  run sudo -n apt-get install -y cmake zlib1g-dev libssl-dev pkg-config > "$LOGS/apt.log" 2>&1
  tail -3 "$LOGS/apt.log"; run cmake --version
  ;;
setup)
  [ -x "$DIST/bin/hadoop" ] || die "no base dist"
  [ -d "$SRC" ] || die "no source copy (unit-run.sh makes it)"
  cd "$SRC" || exit 1
  run mvn -B -pl hadoop-common-project/hadoop-common package -Pnative -DskipTests -Dmaven.javadoc.skip=true \
    > "$LOGS/native-build.log" 2>&1
  grep -E "BUILD (SUCCESS|FAILURE)|Total time" "$LOGS/native-build.log"
  NL=$SRC/hadoop-common-project/hadoop-common/target/native/target/usr/local/lib
  run ls -l "$NL" || die "no native lib"
  rm -rf "$RUN"; mkdir -p "$RUN"/{logs,pids,tmp}
  run cp -a "$DIST" "$RUN/hadoop" || die "dist copy"
  run mkdir -p "$RUN/hadoop/lib/native"
  run cp -a "$NL"/libhadoop.so* "$RUN/hadoop/lib/native/" || die "copy native"
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
  <property><name>dfs.blocksize</name><value>16m</value></property>
  <property><name>dfs.heartbeat.interval</name><value>1</value></property>
  <property><name>dfs.namenode.path.based.cache.refresh.interval.ms</name><value>1000</value></property>
  <property><name>dfs.cachereport.intervalMsec</name><value>10000</value></property>
  <property><name>dfs.datanode.max.locked.memory</name><value>0</value></property>
</configuration>
EOF
  run cat "$RUN/conf/core-site.xml" "$RUN/conf/hdfs-site.xml"
  run hadoop version
  run hadoop checknative -a
  echo "+ ulimit -l: $(ulimit -l)"
  ;;
run)
  L=$(ulimit -l); echo "+ ulimit -l: $L"
  [ "$L" = unlimited ] || [ "$L" -ge 1048577 ] || die "RLIMIT_MEMLOCK below 1 GiB"
  hadoop checknative 2>&1 | grep -E '^hadoop:' | grep -q true || die "native hadoop not true"
  echo "+ free -m:"; free -m
  echo "+ ss -ltn on 9000 9870 9864 9866 9867:"; busy=$(ss -ltn | grep -E ':(9000|9870|9864|9866|9867) '); echo "${busy:-  free}"
  [ -z "$busy" ] || die "ports busy"
  run jps
  if [ -d "$RUN/nn" ] || [ -n "$(ls -A "$RUN/logs" 2>/dev/null)" ]; then
    a="$LOGS/aborted-$(date +%H%M%S)"; mkdir -p "$a"; cp -a "$RUN/logs/." "$a/" 2>/dev/null
    echo "+ previous attempt: daemon logs kept in $a; removing nn dn tmp logs pids f512"
    rm -rf "$RUN/nn" "$RUN/dn" "$RUN"/tmp/* "$RUN"/logs/* "$RUN"/pids/* "$RUN/f512"
  fi
  setM 0; setCR 10000
  run hdfs namenode -format -nonInteractive > "$LOGS/format.log" 2>&1 || die "format"
  run hdfs --daemon start namenode || die "nn"
  run hdfs --daemon start datanode || die "dn"
  waitdn 0 || { stopall; die "DN not live"; }
  run hdfs dfsadmin -safemode wait
  run hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor DEBUG
  # B3c workload: 512 MiB = 32 blocks of 16 MiB
  run hdfs dfs -mkdir /cap
  run bash -c "head -c 536870912 /dev/urandom > '$RUN/f512'"
  run hdfs dfs -put "$RUN/f512" /cap/f512 || { stopall; die "put"; }
  run bash -c "hdfs fsck /cap/f512 -files -blocks | grep -cE 'blk_[0-9]+_[0-9]+ len=16777216'"
  run hdfs cacheadmin -addPool p
  # phase 1 (A6): M = 0 first (DN already running with 0), then 64m, 128m, 256m, 1g
  phase1 M0 0
  for spec in 64m:67108864 128m:134217728 256m:268435456 1g:1073741824; do
    restart_dn "${spec%%:*}" "${spec#*:}"
    phase1 "M${spec%%:*}" "${spec#*:}"
  done
  # phase 2 (A7): M = 128m, cache report interval 60 s, restart both daemons
  setCR 60000; setM 128m
  run hdfs --daemon stop datanode; run hdfs --daemon stop namenode; sleep 3
  run hdfs --daemon start namenode || die "nn restart"
  run hdfs --daemon start datanode || die "dn restart"
  waitdn 134217728 || { stopall; die "DN not live (phase 2)"; }
  run hdfs dfsadmin -safemode wait
  run hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor DEBUG
  for i in $(seq 1 60); do n=$(jmx DataNodeActivity CacheReportsNumOps); [ "${n:-0}" != 0 ] && [ "$n" != None ] && break; sleep 1; done
  echo "first cache report seen: CacheReportsNumOps=$n at $(date '+%T')"
  sleep 8; VBASE=$(vmlck); echo "VmLck baseline (kB) = $VBASE; jmx: $(jmx FSDatasetState CacheUsed CacheCapacity NumBlocksCached)"
  no=$(stat -c %s "$(nnlog)"); dno=$(stat -c %s "$(dnlog)"); t0=$(date +%s.%N)
  run hdfs cacheadmin -addDirective -path /cap/f512 -pool p -replication 1 || die "addDirective (phase 2)"
  run python3 -I "$H/sampler.py" P2-M128m 134217728 "$t0" "$(dnpid)" "$VBASE" "$(nnlog)" "$no" "$(dnlog)" "$dno" \
    "$LOGS/samples-P2-M128m.csv" fixed90
  run hdfs cacheadmin -listDirectives -stats -path /cap/f512
  tail -c +$((no+1)) "$(nnlog)" | grep 'cannot fit in remaining cache size' > "$LOGS/p2-nn-cannot-fit.txt"
  tail -c +$((dno+1)) "$(dnlog)" | grep -E 'DNA_CACHE|DNA_UNCACHE|could not reserve|Failed to cache' > "$LOGS/p2-dn-dna-cache.txt"
  echo "p2 NN cannot-fit lines: $(wc -l < "$LOGS/p2-nn-cannot-fit.txt"); DN lines: $(wc -l < "$LOGS/p2-dn-dna-cache.txt")"
  # cleanup (B3e step 4)
  run hdfs cacheadmin -removeDirectives -path /cap/f512
  waitzero
  run hdfs cacheadmin -removePool p
  stopall
  run jps
  grep -hE 'Starting DataNode with maxLockedMemory' "$RUN"/logs/hadoop-*-datanode-*.log > "$LOGS/dn-maxlocked-excerpt.txt"
  grep -hE 'could not reserve|Failed to cache' "$RUN"/logs/hadoop-*-datanode-*.log > "$LOGS/dn-reserve-fail-excerpt.txt"
  grep -h 'cannot fit in remaining cache size' "$RUN"/logs/hadoop-*-namenode-*.log > "$LOGS/nn-cannot-fit-all.txt"
  echo "all NN cannot-fit lines: $(wc -l < "$LOGS/nn-cannot-fit-all.txt"); DN reserve failures: $(wc -l < "$LOGS/dn-reserve-fail-excerpt.txt")"
  echo "=== cluster-run.sh run end $(date '+%F %T %Z')"
  ;;
phase2b)
  # 2026-11-25, after run 1's phase 2 (runbook defect D1, results section 3): A7 says the directive is added 8 s after
  # the first cache report that follows the restart. The 'run' mode started polling CacheReportsNumOps only after
  # 'safemode wait', when the first report (sent at DataNode registration) was already counted, so it waited 8 s
  # after a report that was ~30 s old and the window came out ~20 s. This mode repeats phase 2 once (A8 allows one
  # re-run), on the same data, and waits for the counter to CHANGE before the 8 s.
  L=$(ulimit -l); echo "+ ulimit -l: $L"
  busy=$(ss -ltn | grep -E ':(9000|9870|9864|9866|9867) '); [ -z "$busy" ] || die "ports busy"
  grep -E 'max.locked|cachereport' "$RUN/conf/hdfs-site.xml"
  setCR 60000; setM 128m
  run hdfs --daemon start namenode || die "nn start"
  run hdfs --daemon start datanode || die "dn start"
  waitdn 134217728 || { stopall; die "DN not live (phase 2b)"; }
  run hdfs dfsadmin -safemode wait
  run hadoop daemonlog -setlevel localhost:9870 org.apache.hadoop.hdfs.server.blockmanagement.CacheReplicationMonitor DEBUG
  run hdfs cacheadmin -addPool p
  c0=$(jmx DataNodeActivity CacheReportsNumOps); echo "CacheReportsNumOps at poll start: $c0 at $(date '+%T')"
  for i in $(seq 1 90); do n=$(jmx DataNodeActivity CacheReportsNumOps); [ "$n" != "$c0" ] && break; sleep 1; done
  echo "next cache report seen: CacheReportsNumOps=$n at $(date '+%T')"
  [ "$n" != "$c0" ] || { stopall; die "no cache report within 90 s"; }
  sleep 8; VBASE=$(vmlck); echo "VmLck baseline (kB) = $VBASE; jmx: $(jmx FSDatasetState CacheUsed CacheCapacity NumBlocksCached)"
  no=$(stat -c %s "$(nnlog)"); dno=$(stat -c %s "$(dnlog)"); t0=$(date +%s.%N)
  run hdfs cacheadmin -addDirective -path /cap/f512 -pool p -replication 1 || die "addDirective (phase 2b)"
  run python3 -I "$H/sampler.py" P2b-M128m 134217728 "$t0" "$(dnpid)" "$VBASE" "$(nnlog)" "$no" "$(dnlog)" "$dno" \
    "$LOGS/samples-P2b-M128m.csv" fixed90
  run hdfs cacheadmin -listDirectives -stats -path /cap/f512
  tail -c +$((no+1)) "$(nnlog)" | grep 'cannot fit in remaining cache size' > "$LOGS/p2b-nn-cannot-fit.txt"
  tail -c +$((no+1)) "$(nnlog)" | grep -E 'addDirective|removeDirective' > "$LOGS/p2b-nn-directive-ops.txt"
  tail -c +$((dno+1)) "$(dnlog)" | grep -E 'DNA_CACHE|DNA_UNCACHE|could not reserve|Failed to cache' > "$LOGS/p2b-dn-dna-cache.txt"
  echo "p2b NN cannot-fit lines: $(wc -l < "$LOGS/p2b-nn-cannot-fit.txt"); DN lines: $(wc -l < "$LOGS/p2b-dn-dna-cache.txt")"
  run hdfs cacheadmin -removeDirectives -path /cap/f512
  waitzero
  run hdfs cacheadmin -removePool p
  stopall
  run jps
  echo "=== cluster-run.sh phase2b end $(date '+%F %T %Z')"
  ;;
stop) stopall ;;
esac
