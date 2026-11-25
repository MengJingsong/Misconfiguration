#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + A5, A6) for dfs.client.socketcache.capacity-putInternal-capacity--autonomous.
# Run on the stage-4 node:  cluster-run.sh <R> <harness-dir>
# $RUN = <R>/cluster. Logs every command and its output to $RUN/../logs/cluster/cluster-run.log.
set -uo pipefail
R=${1:?R}; HD=${2:?harness dir}
RUN=$R/cluster
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH
ulimit -n 65536
L=$R/logs/cluster; mkdir -p "$L"; LOG=$L/cluster-run.log
run() { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; return ${PIPESTATUS[0]}; }
die() { echo "STOP: $*" | tee -a "$LOG"; stop_all; exit 1; }
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf HADOOP_LOG_DIR=$RUN/logs HADOOP_PID_DIR=$RUN/pids
export HADOOP_HEAPSIZE_MAX=1g HDFS_DATANODE_OPTS="-XX:NativeMemoryTracking=summary"
export PATH=$HADOOP_HOME/bin:$PATH
stop_all() {
  [ -x "$HADOOP_HOME/bin/hdfs" ] || return 0
  hdfs --daemon stop datanode 2>&1 | tee -a "$LOG"
  hdfs --daemon stop namenode 2>&1 | tee -a "$LOG"
  sleep 3
  echo "leftover: $(ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[R]unJar|PeerCacheProbe' | grep -v grep | grep "$RUN" )" | tee -a "$LOG"
}
echo "=== cluster-run start $(date -Is) host=$(hostname) ulimit-n=$(ulimit -n)" | tee -a "$LOG"
run md5sum "$HD"/PeerCacheProbe.java "$HD"/sample.sh "$0"
for p in 9000 9866 9864 9867 9870 9868; do ss -ltn | grep -q ":$p " && die "port $p busy"; done
# B3a/A5: distribution copy and configuration
mkdir -p "$RUN" "$RUN/logs" "$RUN/pids" "$RUN/tmp"
run cp -a "$DIST" "$RUN/hadoop" || die "copy dist"
run cp -r "$RUN/hadoop/etc/hadoop" "$RUN/conf"
cat > "$RUN/conf/core-site.xml" <<X
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:9000</value></property>
  <property><name>hadoop.tmp.dir</name><value>$RUN/tmp</value></property>
</configuration>
X
cat > "$RUN/conf/hdfs-site.xml" <<X
<?xml version="1.0"?>
<configuration>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>$RUN/nn</value></property>
  <property><name>dfs.datanode.data.dir</name><value>$RUN/dn</value></property>
  <property><name>dfs.datanode.socket.reuse.keepalive</name><value>600000</value></property>
  <property><name>dfs.datanode.max.transfer.threads</name><value>4096</value></property>
</configuration>
X
run cat "$RUN/conf/core-site.xml" "$RUN/conf/hdfs-site.xml"
run hadoop version
# probe jar
mkdir -p "$RUN/probe"
run javac -cp "$(hadoop classpath)" -d "$RUN/probe" "$HD/PeerCacheProbe.java" || die "javac"
run jar cf "$RUN/probe.jar" -C "$RUN/probe" . || die "jar"
# B3e step 1: format and start
run hdfs namenode -format -nonInteractive || die "format"
run hdfs --daemon start namenode || die "nn start"
run hdfs --daemon start datanode || die "dn start"
run hdfs dfsadmin -safemode wait
sleep 5
run jps
DNPID=$(cat "$HADOOP_PID_DIR"/hadoop-*-datanode.pid); NNPID=$(cat "$HADOOP_PID_DIR"/hadoop-*-namenode.pid)
echo "DNPID=$DNPID NNPID=$NNPID" | tee -a "$LOG"
run hdfs getconf -confKey dfs.datanode.socket.reuse.keepalive
run hdfs getconf -confKey dfs.client.socketcache.capacity
# B3c: workload
mkdir -p "$RUN/files"
for i in $(seq 0 1023); do head -c 262144 /dev/urandom > "$RUN/files/f$i"; done
run hdfs dfs -put "$RUN/files" /probe || die "put"
echo "ls-count=$(hdfs dfs -ls /probe | wc -l)" | tee -a "$LOG"
run hdfs dfs -du -s /probe
# B3e step 3: baseline DN sample
bash "$HD/sample.sh" baseline - "$DNPID" | tee -a "$LOG" | tee -a "$L/samples.txt"
waitfor() {  # waitfor <file> <pattern> <timeout-s> <pid>
  local t=0; until grep -q "$2" "$1" 2>/dev/null; do sleep 1; t=$((t+1)); [ $t -ge $3 ] && return 1; kill -0 $4 2>/dev/null || { grep -q "$2" "$1" && return 0; return 1; }; done; return 0; }
xc() { curl -s 'http://localhost:9864/jmx?qry=Hadoop:service=DataNode,name=DataNodeInfo' | grep -o '"XceiverCount" *: *[0-9]*' | grep -o '[0-9]*$'; }
BASEX=$(xc); echo "baseline XceiverCount=$BASEX" | tee -a "$LOG"
for REP in 1 2; do for C in 0 16 256 1024; do
  TAG="C$C-r$REP"; OUT=$L/out-$TAG.txt
  echo "--- run $TAG start $(date -Is)" | tee -a "$LOG"
  echo "du-before $TAG $(du -sb $RUN/dn $RUN/nn $RUN/tmp $RUN/logs | tr '\t\n' ': ')" | tee -a "$LOG" "$L/du.txt"
  bash "$HD/sample.sh" "$TAG-pre" - "$DNPID" | tee -a "$LOG" "$L/samples.txt"
  HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC -XX:NativeMemoryTracking=summary" \
    hadoop jar "$RUN/probe.jar" PeerCacheProbe -D dfs.client.socketcache.capacity=$C \
    -D dfs.client.socketcache.expiryMsec=600000 1024 /probe 60000 > "$OUT" 2>&1 &
  CPID=$!
  echo "client pid $CPID ($TAG); jps: $(jps | grep -E "^$CPID ")" | tee -a "$LOG"
  for W in START:0 OPEN:1 CLOSED:2; do
    PH=${W%%:*}; WN=${W##*:}
    waitfor "$OUT" "^PHASE $PH " 600 $CPID || { cat "$OUT" | tail -20 | tee -a "$LOG"; kill $CPID; die "no PHASE $PH in $TAG"; }
    sleep 20
    bash "$HD/sample.sh" "$TAG-w$WN" "$CPID" "$DNPID" | tee -a "$LOG" "$L/samples.txt"
  done
  wait $CPID; echo "client exit $? ($TAG)" | tee -a "$LOG"
  grep -E "^(PROBE|PHASE|BYTES)" "$OUT" | sed "s/^/$TAG /" | tee -a "$LOG" "$L/phase-lines.txt"
  sleep 10
  bash "$HD/sample.sh" "$TAG-post10" - "$DNPID" | tee -a "$LOG" "$L/samples.txt"
  echo "du-after $TAG $(du -sb $RUN/dn $RUN/nn $RUN/tmp $RUN/logs | tr '\t\n' ': ')" | tee -a "$LOG" "$L/du.txt"
  t=0; while X=$(xc); [ $((X - BASEX)) -gt 2 ] && [ $t -lt 60 ]; do sleep 2; t=$((t+2)); done
  echo "XceiverCount before next run: $X (after ${t}s extra)" | tee -a "$LOG"
done; done
# B4 cleanup
run hdfs dfs -du -s /probe
stop_all
echo "=== cluster-run end $(date -Is)" | tee -a "$LOG"
