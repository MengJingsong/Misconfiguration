#!/usr/bin/env bash
# Cluster tier (case-file B3e, amended A4-A6, 2026-11-25) for
# dfs.data.transfer.max.packet.size-initWritePacketSize-PacketReceiver.MAX_PACKET_SIZE--autonomous.
# Usage (on the node): cluster-run.sh <run-dir>     (<run-dir>/harness holds this folder)
# One NameNode + one DataNode (hdfs --daemon), client JVM per command with JFR; logs every command.
# Stops at the first failed set-up step; always stops the daemons it started (trap).
set -uo pipefail
RUN=${1:?usage: cluster-run.sh <run-dir>}
HERE=$(cd "$(dirname "$0")" && pwd)
C=$RUN/cluster
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export HADOOP_HOME=$C/hadoop
export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$PATH
export HADOOP_LOG_DIR=$C/logs HADOOP_PID_DIR=$C/pids
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
OUT=$RUN/logs/cluster
mkdir -p "$OUT"
LOG=$OUT/cluster-run.log
exec > >(tee -a "$LOG") 2>&1
step(){ echo "+ [$(date '+%F %T')] $*"; "$@"; }
die(){ echo "STOP: $*"; exit 1; }
daemons(){ ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode' | grep -F "$C" || true; }
stop_all(){
  echo "+ [$(date '+%F %T')] stopping daemons"
  HADOOP_CONF_DIR=$C/conf-dn hdfs --daemon stop datanode || true
  HADOOP_CONF_DIR=$C/conf-dn hdfs --daemon stop namenode || true
  sleep 3
  echo "daemons left:"; daemons
  echo "jps:"; jps -l | grep -v -E 'Jps$' || true
}
trap 'rc=$?; stop_all; echo "EXIT rc=$rc at $(date "+%F %T")"' EXIT

echo "=== cluster-run.sh $(date '+%F %T') on $(hostname)"
step java -version
step md5sum "$HERE/cluster-run.sh" "$HERE/jfr-read.py"
for p in 19000 19864 19865 19866 19867 19870 19871; do
  ss -ltn | awk '{print $4}' | grep -q ":$p\$" && die "port $p in use"
done
echo "ports 19000 19864-19867 19870 19871 free"

# ---- B3a: distribution, configs (A4)
[ -e "$C" ] && die "$C exists (start clean)"
mkdir -p "$C"/{logs,pids,tmp,nn,dn,jfr,dumps,in,out}
step cp -a "$DIST" "$C/hadoop"
step "$C/hadoop/bin/hadoop" version
step cp -r "$C/hadoop/etc/hadoop" "$C/conf-dn"
cat > "$C/conf-dn/core-site.xml" <<X
<?xml version="1.0"?>
<configuration>
<property><name>fs.defaultFS</name><value>hdfs://localhost:19000</value></property>
<property><name>hadoop.tmp.dir</name><value>$C/tmp</value></property>
</configuration>
X
hdfs_site(){ cat <<X
<?xml version="1.0"?>
<configuration>
<property><name>dfs.replication</name><value>1</value></property>
<property><name>dfs.namenode.name.dir</name><value>$C/nn</value></property>
<property><name>dfs.datanode.data.dir</name><value>$C/dn</value></property>
<property><name>dfs.namenode.http-address</name><value>localhost:19870</value></property>
<property><name>dfs.namenode.https-address</name><value>localhost:19871</value></property>
<property><name>dfs.datanode.address</name><value>localhost:19866</value></property>
<property><name>dfs.datanode.http.address</name><value>localhost:19864</value></property>
<property><name>dfs.datanode.https.address</name><value>localhost:19865</value></property>
<property><name>dfs.datanode.ipc.address</name><value>localhost:19867</value></property>
$1
</configuration>
X
}
hdfs_site "" > "$C/conf-dn/hdfs-site.xml"
step cp -r "$C/conf-dn" "$C/conf-c16"
step cp -r "$C/conf-dn" "$C/conf-c4"
hdfs_site "<property><name>dfs.data.transfer.max.packet.size</name><value>4194304</value></property>" > "$C/conf-c4/hdfs-site.xml"
step grep -c max.packet.size "$C/conf-dn/hdfs-site.xml" "$C/conf-c16/hdfs-site.xml" "$C/conf-c4/hdfs-site.xml"

# (attempt 2) the inputs are written without step(): step() echoes to stdout, which went into the file
echo "+ [$(date '+%F %T')] head -c 1048576 /dev/urandom > $C/in/f1m; head -c 50331648 /dev/urandom > $C/in/f48m"
head -c 1048576 /dev/urandom > "$C/in/f1m"
head -c 50331648 /dev/urandom > "$C/in/f48m"
ls -l "$C/in"
[ "$(stat -c %s "$C/in/f1m")" = 1048576 ] && [ "$(stat -c %s "$C/in/f48m")" = 50331648 ] || die "input sizes wrong"

# ---- format and start (A4, A6)
export HADOOP_CONF_DIR=$C/conf-dn HADOOP_HEAPSIZE_MAX=1g
step hdfs namenode -format -nonInteractive > "$OUT/format.log" 2>&1 || die "format failed"
step hdfs --daemon start namenode || die "namenode start"
step hdfs --daemon start datanode || die "datanode start"
ok=0
for i in $(seq 1 60); do
  if hdfs dfsadmin -report 2>/dev/null | grep -q "Live datanodes (1)"; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || die "no live datanode"
step jps -l
step hdfs dfsadmin -safemode wait
step hdfs dfs -mkdir -p /t
unset HADOOP_HEAPSIZE_MAX
DNLOG=$(ls "$C"/logs/hadoop-*-datanode-*.log | head -1)
echo "DataNode log: $DNLOG"

# ---- one client run: tag conf C H file
client(){
  local tag=$1 conf=$2 cpkt=$3 heap=$4 file=$5
  local dn0; dn0=$(grep -c "Incorrect value for packet payload size" "$DNLOG")
  echo "+ [$(date '+%F %T')] CLIENT tag=$tag conf=$conf C=$cpkt H=$heap file=$file"
  local t0; t0=$(date +%s.%N)
  HADOOP_CONF_DIR=$C/$conf \
  HADOOP_CLIENT_OPTS="-XX:TLABSize=16k -XX:-ResizeTLAB -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=$C/dumps/$tag.hprof -XX:StartFlightRecording=filename=$C/jfr/$tag.jfr,settings=profile,dumponexit=true -Xmx$heap" \
    hdfs dfs -D dfs.client-write-packet-size=$cpkt -put -f "$C/in/$file" "/t/$tag" > "$C/out/$tag.out" 2>&1
  local rc=$?
  local t1; t1=$(date +%s.%N)
  local dn1; dn1=$(grep -c "Incorrect value for packet payload size" "$DNLOG")
  local warn; warn=$(grep -c "Configured write packet exceeds" "$C/out/$tag.out")
  local oom; oom=$(grep -c "OutOfMemoryError" "$C/out/$tag.out")
  local len; len=$(HADOOP_CONF_DIR=$C/conf-dn hdfs dfs -stat %b "/t/$tag" 2>/dev/null || echo absent)
  local dump="none"; [ -f "$C/dumps/$tag.hprof" ] && dump=$(stat -c %s "$C/dumps/$tag.hprof")
  local jfrl="none"
  if [ -f "$C/jfr/$tag.jfr" ]; then
    jfr print --json --stack-depth 64 --events jdk.ObjectAllocationOutsideTLAB,jdk.ObjectAllocationInNewTLAB,jdk.GCHeapConfiguration,jdk.JVMInformation "$C/jfr/$tag.jfr" > "$C/jfr/$tag.json" 2> "$C/jfr/$tag.json.err"
    jfrl=$(python3 -I "$HERE/jfr-read.py" "$C/jfr/$tag.json" "$tag")
  fi
  echo "READING,tag=$tag,conf=$conf,C=$cpkt,H=$heap,file=$file,rc=$rc,secs=$(echo "$t1 - $t0" | bc),clientWarn=$warn,oom=$oom,dnIncorrectPayload+=$((dn1-dn0)),hdfsLen=$len,heapDump=$dump" | tee -a "$OUT/readings.csv"
  echo "$jfrl" | tee -a "$OUT/readings.csv"
  echo "--- client stderr (head/tail) $tag"; head -5 "$C/out/$tag.out"; echo "..."; grep -E "WARN|Exception|Error" "$C/out/$tag.out" | head -8
  [ "$dn1" -gt "$dn0" ] && { echo "--- DN log new lines (first 3)"; grep "Incorrect value for packet payload size" "$DNLOG" | tail -n $((dn1-dn0)) | head -3; }
  HADOOP_CONF_DIR=$C/conf-dn hdfs fsck "/t/$tag" -files -blocks 2>/dev/null | grep -E "^/t|Status|bytes" | head -4
  HADOOP_CONF_DIR=$C/conf-dn hdfs dfs -rm -f -skipTrash '/t/*' > /dev/null 2>&1
  rm -f "$C/jfr/$tag.json"
}

# ---- B3e step 2: set 1 (client MAX 16M, DN 16M, H 1024m)
for cp in 65536 16777216 33554432 268435456; do
  for f in f1m f48m; do client "s1-$cp-$f" conf-c16 $cp 1024m $f; done
done
# ---- step 3: set 2 / 2-ctl (H 192m, f1m)
client s2-268435456-f1m conf-c16 268435456 192m f1m
client s2ctl-16777216-f1m conf-c16 16777216 192m f1m
# ---- step 4: set 3 (client MAX 4M via conf-c4, DN 16M)
for cp in 4194304 8388608; do
  for f in f1m f48m; do client "s3-$cp-$f" conf-c4 $cp 1024m $f; done
done
echo "=== runs done $(date '+%F %T')"
# step 5 (A6) in the EXIT trap: hdfs --daemon stop, then the process check
