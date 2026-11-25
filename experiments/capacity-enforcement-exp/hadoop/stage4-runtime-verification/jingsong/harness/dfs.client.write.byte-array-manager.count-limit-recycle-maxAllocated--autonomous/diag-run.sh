#!/usr/bin/env bash
# Diagnostic after the cluster tier (not a reading of the case, no effect on the verdict): restart the
# run's HDFS, run BamProbe disabled x2 and L8 x1 with the same arguments as cluster-run.sh, take a
# heap dump (live objects) when the probe prints POSTGC, and list byte[] lengths in each dump.
# Purpose: explain why the disabled baseline holds more byte[] than the capped runs' non-pool part.
set -euo pipefail
R=/mydata/jingsong-s4/dfs.client.write.byte-array-manager.count-limit-recycle-maxAllocated-run1
OUT=$R/logs/diag-cluster
mkdir -p "$OUT"
exec > >(tee -a "$OUT/diag-run.log") 2>&1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$R/hadoop/bin:$PATH
export HADOOP_HOME=$R/hadoop HADOOP_CONF_DIR=$R/conf HADOOP_LOG_DIR=$R/logs/hadoop HADOOP_PID_DIR=$R/pids
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
PROBE_PID=""
cleanup() {
  if [ -n "$PROBE_PID" ] && kill -0 "$PROBE_PID" 2>/dev/null; then kill "$PROBE_PID" || true; sleep 2; kill -9 "$PROBE_PID" 2>/dev/null || true; fi
  env HADOOP_HEAPSIZE_MAX=1g hdfs --daemon stop datanode || true
  env HADOOP_HEAPSIZE_MAX=1g hdfs --daemon stop namenode || true
  sleep 3
  echo "leftover processes of this run (must be none):"
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[B]amProbe' | grep -F "$R" || echo "none"
}
trap cleanup EXIT
run env HADOOP_HEAPSIZE_MAX=1g hdfs --daemon start namenode
run env HADOOP_HEAPSIZE_MAX=1g hdfs --daemon start datanode
sleep 10
run timeout 300 hdfs dfsadmin -safemode wait
for spec in "dx1 false 2048 0" "dx2 false 2048 0" "Lx8 true 8 0"; do
  set -- $spec; id=$1
  echo "=== diag $id $(date '+%F %T %Z')"
  hdfs dfs -rm -r -skipTrash /bam > /dev/null 2>&1 || true
  hdfs dfs -mkdir -p /bam
  PLOG="$OUT/probe-$id.log"
  HADOOP_CLIENT_OPTS="-Xmx1g -XX:+UseSerialGC" HADOOP_CLASSPATH="$R/probe" \
    timeout 900 hadoop org.apache.hadoop.hdfs.util.BamProbe "$id" "$2" "$3" "$4" 64 67108864 "/bam/$id" 30 > "$PLOG" 2>&1 &
  TPID=$!
  for i in $(seq 1 120); do grep -q ' ENV ' "$PLOG" && break; sleep 1; done
  PROBE_PID=$(grep -m1 ' ENV ' "$PLOG" | sed -E 's/.*pid=([0-9]+)@.*/\1/')
  for i in $(seq 1 900); do grep -q ' POSTGC ' "$PLOG" && break; kill -0 "$PROBE_PID" 2>/dev/null || break; sleep 1; done
  grep ' POSTGC ' "$PLOG"
  jcmd "$PROBE_PID" GC.class_histogram | grep -E ' \[B$' || true
  jcmd "$PROBE_PID" GC.heap_dump "$OUT/$id.hprof"
  python3 -I "$R/harness/hprof_bytearrays.py" "$OUT/$id.hprof" | tee "$OUT/bytearrays-$id.txt" | head -12
  rc=0; wait "$TPID" || rc=$?; PROBE_PID=""
  echo "PROBE-EXIT $id rc=$rc"
  rm -f "$OUT/$id.hprof"
done
hdfs dfs -rm -r -skipTrash /bam > /dev/null 2>&1 || true
