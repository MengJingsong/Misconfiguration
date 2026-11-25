#!/usr/bin/env bash
# Cluster tier (B3, with the audit amendments of 2026-11-25) for nfs.max.open.files-put-maxStreams--autonomous.
# Runs ON the node (pc75). Pseudo-distributed: NameNode + DataNode via `hdfs --daemon`, NFS gateway via the
# Option C launcher (no portmapper registration; the host's rpcbind is not touched).
# Usage: cluster-run.sh compile | setup | arm <label> <K|unset> <chunk> | all | teardown
# Every command and its output goes to $R/logs/cluster-run.log.
set -uo pipefail
R=/mydata/jingsong-s4/nfs.max.open.files-put-maxStreams-run1
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
H=$R/hadoop
CONF=$R/conf
OUT=$R/logs/cluster
HC=$R/harness/classes
U=$(whoami)
M=64; OFFSET=1048576; HOLD=120
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$H HADOOP_CONF_DIR=$CONF
export PATH=$JAVA_HOME/bin:$H/bin:$PATH
mkdir -p "$OUT" "$R/logs" "$R/pids"
exec > >(tee -a "$R/logs/cluster-run.log") 2>&1
run() { echo "+ [$(date '+%F %T %Z')] $*"; "$@"; }
fail() { echo "STOP: $*"; exit 1; }
prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
gwpid() { jps 2>/dev/null | awk '$2=="NfsLauncher"{print $1}'; }
ports_busy() { ss -ltn | awk '{print $4}' | grep -E ':(9000|9864|9865|9866|9867|9870|2049|4242)$'; }

do_compile() {
  echo "=== compile $(date '+%F %T %Z')"
  [ -x "$H/bin/hadoop" ] || run cp -a "$DIST" "$H"
  mkdir -p "$HC"
  run javac -d "$HC" -cp "$("$H/bin/hadoop" classpath)" "$R/harness/NfsStreamLoad.java" "$R/harness/NfsLauncher.java" \
    || fail "javac"
  run ls -l "$HC"
}

write_hdfs_site() {  # $1 = K or "unset"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop dfs.replication 1
    prop dfs.namenode.name.dir "$R/nn"
    prop dfs.datanode.data.dir "$R/dn"
    prop nfs.dump.dir "$R/nfsdump"
    [ "$1" = unset ] || prop nfs.max.open.files "$1"
    prop nfs.stream.timeout 600000
    prop nfs.exports.allowed.hosts '* rw'
    echo '</configuration>'; } > "$CONF/hdfs-site.xml"
}

do_setup() {
  echo "=== setup $(date '+%F %T %Z') on $(hostname)"
  [ -z "$(ports_busy)" ] || fail "ports in use: $(ports_busy)"
  [ -x "$H/bin/hadoop" ] || run cp -a "$DIST" "$H"
  rm -rf "$CONF"; run cp -r "$H/etc/hadoop" "$CONF"
  mkdir -p "$R/tmp" "$R/nn" "$R/dn" "$R/logs/hadoop" "$R/nfsdump"
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop fs.defaultFS hdfs://localhost:9000
    prop hadoop.tmp.dir "$R/tmp"
    prop hadoop.proxyuser.$U.hosts '*'
    prop hadoop.proxyuser.$U.groups '*'
    echo '</configuration>'; } > "$CONF/core-site.xml"
  write_hdfs_site 8
  cat >> "$CONF/hadoop-env.sh" <<EOF
export JAVA_HOME=$JAVA_HOME
export HADOOP_LOG_DIR=$R/logs/hadoop
export HADOOP_PID_DIR=$R/pids
EOF
  echo 'log4j.logger.org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtxCache=DEBUG' >> "$CONF/log4j.properties"
  run cat "$CONF/core-site.xml" "$CONF/hdfs-site.xml"
  run tail -3 "$CONF/hadoop-env.sh"; run tail -1 "$CONF/log4j.properties"
  run hdfs namenode -format -nonInteractive > "$OUT/nn-format.log" 2>&1 || fail "format"
  run hdfs --daemon start namenode
  run hdfs --daemon start datanode
  run hdfs dfsadmin -safemode wait
  for i in $(seq 1 30); do
    hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' && break; sleep 2
  done
  run hdfs dfsadmin -report | head -14
  hdfs dfsadmin -report 2>/dev/null | grep -q 'Live datanodes (1)' || fail "no live DN"
  run jps
}

start_gateway() {  # $1 = arm dir
  [ -z "$(gwpid)" ] || fail "a gateway is already running"
  ss -ltn | awk '{print $4}' | grep -qE ':(2049|4242)$' && fail "2049/4242 busy"
  HADOOP_CLASSPATH=$HC HADOOP_CLIENT_OPTS="-Xms1g -Xmx1g" nohup "$H/bin/hadoop" --config "$CONF" s4.NfsLauncher \
    > "$1/gateway.log" 2>&1 < /dev/null &
  echo $! > "$R/pids/launcher.pid"
  for i in $(seq 1 60); do
    sleep 1
    grep -q 'NFS3 LAUNCHER STARTED' "$1/gateway.log" && ss -ltn | awk '{print $4}' | grep -qE ':2049$' && break
  done
  grep -q 'NFS3 LAUNCHER STARTED' "$1/gateway.log" || { tail -30 "$1/gateway.log"; fail "gateway did not start"; }
  echo "gateway pid $(gwpid) (launcher.pid $(cat "$R/pids/launcher.pid"))"
  run grep -E 'Maximum open streams is|Stream timeout is' "$1/gateway.log"
}

stop_gateway() {
  local p; p=$(gwpid)
  [ -n "$p" ] && run kill "$p"
  for i in $(seq 1 15); do [ -z "$(gwpid)" ] && break; sleep 1; done
  p=$(gwpid); [ -n "$p" ] && { echo "gateway still alive, kill -9 $p"; kill -9 "$p"; sleep 1; }
  rm -f "$R/pids/launcher.pid"
  true
}

sample() {  # $1 tag, $2 arm dir, $3 pid, $4 runid
  local tag=$1 A=$2 P=$3 RID=$4
  local t; t=$(date +%s.%N)
  jcmd "$P" GC.run > /dev/null 2>&1
  [ "$tag" = base ] && { sleep 1; jcmd "$P" GC.run > /dev/null 2>&1; }
  jcmd "$P" GC.class_histogram > "$A/histo-$tag.txt" 2>&1
  jcmd "$P" GC.heap_info > "$A/heapinfo-$tag.txt" 2>&1
  jstack "$P" > "$A/jstack-$tag.txt" 2>&1
  hdfs dfsadmin -listOpenFiles > "$A/openfiles-$tag.txt" 2>&1
  local ofc wc dos bb used str opn dn db rss thr
  ofc=$(awk '$4=="org.apache.hadoop.hdfs.nfs.nfs3.OpenFileCtx"{print $2}' "$A/histo-$tag.txt")
  wc=$(awk '$4=="org.apache.hadoop.hdfs.nfs.nfs3.WriteCtx"{print $2}' "$A/histo-$tag.txt")
  dos=$(awk '$4=="org.apache.hadoop.hdfs.DFSOutputStream"{print $2}' "$A/histo-$tag.txt")
  bb=$(awk '$4=="[B"{print $3}' "$A/histo-$tag.txt")
  used=$(grep -E 'PSYoungGen|ParOldGen' "$A/heapinfo-$tag.txt" | sed -E 's/.*used ([0-9]+)K.*/\1/' | awk '{s+=$1} END{print s}')
  # fix of 2026-11-25 (runbook defect 3): count threads whose stack runs DataStreamer.run (unnamed until a pipeline exists)
  str=$(grep -c 'at org.apache.hadoop.hdfs.DataStreamer.run(' "$A/jstack-$tag.txt")
  local strn; strn=$(grep -c '^"DataStreamer for file' "$A/jstack-$tag.txt")
  local dsi; dsi=$(awk '$4=="org.apache.hadoop.hdfs.DataStreamer"{print $2}' "$A/histo-$tag.txt")
  thr=$(grep -c '^"' "$A/jstack-$tag.txt")
  opn=$(grep -c "nfsload-$RID-" "$A/openfiles-$tag.txt")
  dn=$(find "$R/nfsdump" -type f | wc -l)
  db=$(du -sb "$R/nfsdump" | cut -f1)
  rss=$(awk '/VmRSS/{print $2}' /proc/"$P"/status)
  echo "SAMPLE tag=$tag t=$t OpenFileCtx=${ofc:-0} WriteCtx=${wc:-0} DFSOutputStream=${dos:-0} B_bytes=${bb:-0} heapUsedK=${used:-0} streamers=$str namedStreamers=$strn DataStreamerObj=${dsi:-0} threads=$thr openFiles=$opn dumpFiles=$dn dumpBytes=$db rssK=${rss:-0}" \
    | tee -a "$A/samples.txt"
}

do_arm() {  # label K chunk
  local label=$1 k=$2 chunk=$3
  local A=$OUT/arm-$label RID="${label}-$(date +%H%M%S)"
  rm -rf "$A"; mkdir -p "$A"
  echo "=== arm $label K=$k chunk=$chunk runid=$RID $(date '+%F %T %Z')"
  stop_gateway
  write_hdfs_site "$k"
  run grep -E 'nfs\.' "$CONF/hdfs-site.xml"
  cp "$CONF/hdfs-site.xml" "$A/hdfs-site.xml"
  start_gateway "$A"
  local P; P=$(gwpid)
  echo "$P" > "$A/gateway.pid"
  sample base "$A" "$P" "$RID"
  java -Xmx256m -cp "$("$H/bin/hadoop" classpath):$HC" NfsStreamLoad $M "$chunk" $OFFSET "$RID" "$(id -u)" "$(id -g)" $HOLD \
    > "$A/client.txt" 2>&1 &
  local C=$!
  echo "client pid $C"
  local sent=""
  for i in $(seq 1 120); do
    sent=$(awk '/^SENT /{print $2}' "$A/client.txt"); [ -n "$sent" ] && break
    kill -0 $C 2>/dev/null || break; sleep 0.5
  done
  [ -n "$sent" ] || { cat "$A/client.txt"; kill $C 2>/dev/null; stop_gateway; fail "client did not reach SENT"; }
  run grep -E '^(ARGS|SUMMARY|SENT)' "$A/client.txt"
  local s0=$((sent / 1000))
  for off in 15 45 90; do
    local now; now=$(date +%s); [ $((s0 + off)) -gt "$now" ] && sleep $((s0 + off - now))
    sample "s$off" "$A" "$P" "$RID"
  done
  wait $C; echo "client exit $?"
  run tail -1 "$A/client.txt"
  for p in "Maximum open streams is" "Can't add new stream" "Can't add more stream" "All opened streams are busy" \
           "No eviction candidate" "Evict stream ctx"; do
    echo "LOGCOUNT $p: $(grep -cF "$p" "$A/gateway.log")"
  done | tee "$A/logcounts.txt"
  stop_gateway
  run hdfs dfs -rm -skipTrash "/nfsload-$RID-*" > "$A/rm.txt" 2>&1
  run tail -1 "$A/rm.txt"
  echo "=== arm $label end $(date '+%F %T %Z')"
}

do_teardown() {
  echo "=== teardown $(date '+%F %T %Z')"
  stop_gateway
  run hdfs --daemon stop datanode
  run hdfs --daemon stop namenode
  sleep 3
  run jps
  ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode|[N]fsLauncher|[N]fsStreamLoad|[N]fs3' || echo "no daemon left"
  ports_busy || echo "no run port in use"
}

case ${1:-} in
  compile) do_compile ;;
  setup) do_setup ;;
  arm) do_arm "$2" "$3" "$4" ;;
  all)
    for spec in "K8 8 983040" "K32 32 983040" "K128 128 983040" "Kdefault unset 983040" "K8null 8 1"; do
      do_arm $spec || { echo "arm $spec failed"; do_teardown; exit 1; }
    done
    echo "=== ALL ARMS DONE $(date '+%F %T %Z')" ;;
  teardown) do_teardown ;;
  *) fail "usage" ;;
esac
