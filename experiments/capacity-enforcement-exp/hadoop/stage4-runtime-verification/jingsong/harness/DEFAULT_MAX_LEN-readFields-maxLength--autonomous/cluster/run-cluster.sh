#!/usr/bin/env bash
# Stage-4 cluster tier (B3) for DEFAULT_MAX_LEN-readFields-maxLength--autonomous. Runs ON the node.
# Usage: run-cluster.sh <run-dir> <harness-dir>
# Pseudo-distributed NameNode only (B3a), JDK 11 runtime, -Xmx512m, G1 1 MiB regions; arms per B3b/B3c,
# JFR per arm (B3d); logs every command to <run-dir>/cluster/run-cluster.log; stops at the first failure
# and always stops the NameNode on exit.
set -euo pipefail
R=${1:?run dir}; H=${2:?harness dir}
C=$R/cluster; mkdir -p "$C"; LOG=$C/run-cluster.log
exec > >(tee -a "$LOG") 2>&1
step() { echo; echo "=== $(date -Is) STEP: $*"; }
run() { echo "+ $*"; "$@"; }
BASE=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk-amd64
export PATH=$JAVA_HOME/bin:$R/hadoop/bin:$PATH
export HADOOP_HOME=$R/hadoop HADOOP_CONF_DIR=$R/conf HADOOP_LOG_DIR=$R/logs HADOOP_PID_DIR=$R/pids
NNPID=""
cleanup() {
  echo "=== $(date -Is) cleanup: stopping NameNode if running"
  hdfs --daemon stop namenode || true
  sleep 3
  ps -eo pid,cmd | grep -E '[N]ameNode|[N]nTokenProbe' || echo "no NameNode / probe process left"
}
trap cleanup EXIT

step "environment"
run hostname; run uname -r; run java -version; run javac -version

step "B3a distribution (copy of the base build, environment.md section 4) and config"
[ -e "$R/hadoop" ] || run cp -a "$BASE" "$R/hadoop"
run "$R/hadoop/bin/hadoop" version | head -1
rm -rf "$R/conf"; run cp -r "$R/hadoop/etc/hadoop" "$R/conf"
mkdir -p "$R/logs" "$R/pids" "$R/tmp" "$R/name" "$R/probe" "$C/jfr"
RPC=9820; HTTP=9871
for p in $RPC $HTTP; do if ss -ltn | awk '{print $4}' | grep -qE "[:.]$p\$"; then echo "port $p busy"; exit 1; fi; done
echo "ports $RPC $HTTP free"
cat > "$R/conf/core-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:$RPC</value></property>
  <property><name>hadoop.tmp.dir</name><value>$R/tmp</value></property>
  <property><name>hadoop.security.authentication</name><value>simple</value></property>
</configuration>
EOF
cat > "$R/conf/hdfs-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>dfs.namenode.name.dir</name><value>$R/name</value></property>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.http-address</name><value>localhost:$HTTP</value></property>
</configuration>
EOF
cat >> "$R/conf/hadoop-env.sh" <<EOF

# stage-4 o7 (B3a)
export JAVA_HOME=$JAVA_HOME
export HADOOP_LOG_DIR=$R/logs
export HADOOP_PID_DIR=$R/pids
export HDFS_NAMENODE_OPTS="-Xms512m -Xmx512m -XX:+UseG1GC -XX:G1HeapRegionSize=1m -Xlog:gc*:file=$R/logs/nn-gc.log"
EOF
run cat "$R/conf/core-site.xml" "$R/conf/hdfs-site.xml"; run tail -6 "$R/conf/hadoop-env.sh"

step "compile probe and JFR counter"
run cp "$H/NnTokenProbe.java" "$H/JfrCount.java" "$R/probe/"
CP="$(hadoop classpath)"
run javac -cp "$CP" -d "$R/probe" "$R/probe/NnTokenProbe.java"
run javac -d "$R/probe" "$R/probe/JfrCount.java"

step "B3e.1 format"
run hdfs namenode -format -nonInteractive > "$C/format.log" 2>&1; tail -3 "$C/format.log"

step "B3e.2 start NameNode, wait for safe mode OFF"
run hdfs --daemon start namenode
NNPID=$(cat "$R/pids/hadoop-$(whoami)-namenode.pid"); echo "NNPID=$NNPID"
for i in $(seq 1 60); do
  s=$(hdfs dfsadmin -safemode get 2>/dev/null || true); echo "safemode: $s"
  case "$s" in *OFF*) break;; esac
  [ "$i" = 10 ] && hdfs dfsadmin -safemode leave || true
  sleep 3
done
case "$(hdfs dfsadmin -safemode get)" in *OFF*) ;; *) echo "NameNode not out of safe mode"; exit 1;; esac
run jps
run jcmd "$NNPID" VM.command_line
run jcmd "$NNPID" VM.flags
run jcmd "$NNPID" GC.heap_info

step "B3e.3 arms"
READ=$C/readings.txt; : > "$READ"
for arm in "600000 200" "1048575 200" "1048576 200" "1073741824 5"; do
  set -- $arm; L=$1; N=$2
  echo; echo "--- arm L=$L count=$N"
  GCH0=$(grep -ci humongous "$R/logs/nn-gc.log" || true)
  run jcmd "$NNPID" JFR.start name=probe settings=profile filename="$C/jfr/nn-$L.jfr"
  java -cp "$CP:$R/probe" NnTokenProbe "$L" 8 "$N" 2>&1 | tee "$C/probe-$L.log" | grep -E '^(PROBE|TALLY)'
  run jcmd "$NNPID" JFR.stop name=probe
  run jcmd "$NNPID" GC.heap_info | tee "$C/heap-after-$L.txt"
  GCH1=$(grep -ci humongous "$R/logs/nn-gc.log" || true)
  java -cp "$R/probe" JfrCount "$C/jfr/nn-$L.jfr" 500000 | tee "$C/jfrcount-$L.txt"
  echo "ARM L=$L count=$N gcLogHumongousLinesDelta=$((GCH1-GCH0))" | tee -a "$READ"
  grep -E '^TALLY' "$C/probe-$L.log" | tee -a "$READ"
  grep -E '^JFR' "$C/jfrcount-$L.txt" | tee -a "$READ"
  ps -p "$NNPID" > /dev/null && echo "NN alive pid $NNPID" | tee -a "$READ" || { echo "NN DEAD" | tee -a "$READ"; exit 1; }
done

step "B3e.4 health"
run jps
echo "OutOfMemoryError lines in NN logs: $(cat "$R"/logs/*namenode*.log "$R"/logs/*namenode*.out 2>/dev/null | grep -c OutOfMemoryError || true)" | tee -a "$READ"
grep -E 'tried to deserialize|EOFException' "$R"/logs/*namenode*.log | head -5 || true
echo "NN log lines mentioning 'tried to deserialize': $(grep -c 'tried to deserialize' "$R"/logs/*namenode*.log || true)" | tee -a "$READ"
grep -iE 'humongous' "$R/logs/nn-gc.log" | head -20 > "$C/gc-humongous-excerpt.txt" || true

step "B3e.5 stop NameNode"
run hdfs --daemon stop namenode
sleep 3
if ps -p "$NNPID" > /dev/null; then echo "NameNode still running"; exit 1; fi
ps -eo pid,cmd | grep -E '[N]ameNode' || echo "no NameNode process"
trap - EXIT
echo "=== $(date -Is) DONE"
