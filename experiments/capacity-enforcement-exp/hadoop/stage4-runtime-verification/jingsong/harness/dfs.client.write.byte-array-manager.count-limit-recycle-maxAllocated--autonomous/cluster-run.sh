#!/usr/bin/env bash
# Cluster tier (B3 with A5, A6) for
# dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated--autonomous.
# Runs ON the node (pc75): pseudo-distributed HDFS (1 NN + 1 DN) from a copy of the node's built
# distribution, BamProbe client runs, jcmd [B sampling. Logs to $R/logs/cluster-run.log.
# Usage: cluster-run.sh
set -euo pipefail
R=/mydata/jingsong-s4/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated-run1
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
OUT=$R/logs/cluster
LOG=$R/logs/cluster-run.log
mkdir -p "$OUT"
exec > >(tee -a "$LOG") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$R/hadoop/bin:$PATH
export HADOOP_HOME=$R/hadoop
export HADOOP_CONF_DIR=$R/conf
export HADOOP_LOG_DIR=$R/logs/hadoop
export HADOOP_PID_DIR=$R/pids
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
PROBE_PID=""
cleanup() {
  echo "=== cleanup $(date '+%F %T %Z')"
  if [ -n "$PROBE_PID" ] && kill -0 "$PROBE_PID" 2>/dev/null; then kill "$PROBE_PID" || true; sleep 2; kill -9 "$PROBE_PID" 2>/dev/null || true; fi
  HADOOP_HEAPSIZE_MAX=1g hdfs --daemon stop datanode || true
  HADOOP_HEAPSIZE_MAX=1g hdfs --daemon stop namenode || true
  sleep 3
  echo "leftover processes of this run (must be none):"
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[B]amProbe' | grep -F "$R" || echo "none"
}
fail() { echo "STOP: $*"; exit 1; }
trap cleanup EXIT

echo "=== cluster tier start $(date '+%F %T %Z') on $(hostname)"
run java -version
for p in 19300 19370 19371 19366 19364 19367; do
  if ss -ltn "( sport = :$p )" | grep -q LISTEN; then fail "port $p in use"; fi
done
run free -g
run df -h /mydata

# 1. distribution copy and configuration (B3a, A5)
[ -d "$R/hadoop" ] || run cp -a "$DIST" "$R/hadoop"
run "$R/hadoop/bin/hadoop" version | head -1
rm -rf "$R/conf"; run cp -r "$R/hadoop/etc/hadoop" "$R/conf"
cat > "$R/conf/core-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:19300</value></property>
  <property><name>hadoop.tmp.dir</name><value>$R/tmp</value></property>
</configuration>
EOF
cat > "$R/conf/hdfs-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>$R/nn</value></property>
  <property><name>dfs.datanode.data.dir</name><value>$R/dn</value></property>
  <property><name>dfs.blocksize</name><value>268435456</value></property>
  <property><name>dfs.namenode.http-address</name><value>localhost:19370</value></property>
  <property><name>dfs.namenode.https-address</name><value>localhost:19371</value></property>
  <property><name>dfs.datanode.address</name><value>localhost:19366</value></property>
  <property><name>dfs.datanode.http.address</name><value>localhost:19364</value></property>
  <property><name>dfs.datanode.ipc.address</name><value>localhost:19367</value></property>
</configuration>
EOF
run cat "$R/conf/core-site.xml" "$R/conf/hdfs-site.xml"
mkdir -p "$HADOOP_LOG_DIR" "$HADOOP_PID_DIR"

# 2. format and start (A5: --daemon, no SecondaryNameNode)
rm -rf "$R/nn" "$R/dn" "$R/tmp"
run hdfs namenode -format -nonInteractive > "$OUT/format.log" 2>&1 || fail "format failed"
run env HADOOP_HEAPSIZE_MAX=1g hdfs --daemon start namenode
run env HADOOP_HEAPSIZE_MAX=1g hdfs --daemon start datanode
sleep 10
run jps -l
[ "$(ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode' | grep -cF "$R")" = 2 ] || fail "daemons not running"
ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode' | grep -F "$R" | cut -c1-300
run timeout 300 hdfs dfsadmin -safemode wait
run hdfs dfsadmin -report | head -20

# 3. compile the probe
mkdir -p "$R/probe"
run javac -cp "$(hadoop classpath)" -d "$R/probe" "$R/harness/BamProbe.java"

# 4. runs: tag enabled limit threshold ; three repetitions interleaved
RUNS=("disabled false 2048 0" "L8 true 8 0" "L16 true 16 0" "L32 true 32 0" "L4096 true 4096 0" "L8t32 true 8 32")
T=64
S=67108864
for rep in 1 2 3; do
  for spec in "${RUNS[@]}"; do
    set -- $spec
    tag=$1; en=$2; lim=$3; thr=$4
    id="$tag-r$rep"
    echo "=== run $id (enabled=$en limit=$lim threshold=$thr) $(date '+%F %T %Z')"
    hdfs dfs -rm -r -skipTrash /bam > /dev/null 2>&1 || true
    run hdfs dfs -mkdir -p /bam
    PLOG="$OUT/probe-$id.log"
    HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC" HADOOP_CLASSPATH="$R/probe" \
      timeout 900 hadoop org.apache.hadoop.hdfs.util.BamProbe "$id" "$en" "$lim" "$thr" "$T" "$S" "/bam/$id" 60 \
      > "$PLOG" 2>&1 &
    TPID=$!
    # the java pid, from the probe's ENV line
    for i in $(seq 1 120); do grep -q ' ENV ' "$PLOG" && break; sleep 1; done
    PROBE_PID=$(grep -m1 ' ENV ' "$PLOG" | sed -E 's/.*pid=([0-9]+)@.*/\1/')
    echo "probe java pid $PROBE_PID"
    for i in $(seq 1 900); do grep -q ' POSTGC ' "$PLOG" && break; kill -0 "$PROBE_PID" 2>/dev/null || break; sleep 1; done
    grep ' POSTGC ' "$PLOG" || { echo "no POSTGC line"; cat "$PLOG" | tail -50; }
    if grep -q ' POSTGC ' "$PLOG"; then
      for s in 1 2 3; do
        H="$OUT/histo-$id-s$s.txt"
        jcmd "$PROBE_PID" GC.class_histogram > "$H" 2>&1 || true
        echo "SAMPLE $id s$s $(date +%s%3N) $(grep -E ' \[B$' "$H" || echo 'no [B line')"
        [ "$s" = 1 ] && { jcmd "$PROBE_PID" GC.heap_info > "$OUT/heapinfo-$id.txt" 2>&1 || true; }
        [ "$s" -lt 3 ] && sleep 10
      done
    fi
    rc=0; wait "$TPID" || rc=$?
    PROBE_PID=""
    echo "PROBE-EXIT $id rc=$rc"
    grep -E ' (WRITERS-DONE|POSTGC|EXIT|WRITER-FAIL) ' "$PLOG" || true
    echo "DU $id $(hdfs dfs -du -s /bam/$id 2>&1)"
  done
done
hdfs dfs -rm -r -skipTrash /bam > /dev/null 2>&1 || true
echo "=== cluster runs end $(date '+%F %T %Z')"
