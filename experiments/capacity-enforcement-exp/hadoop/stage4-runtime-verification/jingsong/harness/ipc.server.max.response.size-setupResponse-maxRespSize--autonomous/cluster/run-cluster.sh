#!/usr/bin/env bash
# Cluster tier (B3e) for ipc.server.max.response.size-setupResponse-maxRespSize--autonomous.
# Runs ON pc91. Usage: run-cluster.sh <RUN dir> <harness dir>
# Pseudo-distributed HDFS (NN + DN) from the node's built distribution, daemons on JDK 11 (B3a).
set -uo pipefail
RUN=${1:?RUN}; H=${2:?harness}
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
J11=/usr/lib/jvm/java-11-openjdk-amd64
OUT=$RUN/cluster-out; mkdir -p $OUT
exec > >(tee -a $OUT/run-cluster.log) 2>&1
die() { echo "STOP: $*"; exit 2; }
log() { echo "+ $*"; "$@"; }
echo "== $(date) host $(hostname) kernel $(uname -r)"

# ---- B3a: distribution, configuration ----
[ -x $DIST/bin/hadoop ] || die "no distribution at $DIST"
[ -d $RUN/hadoop ] || log cp -a $DIST $RUN/hadoop
export HADOOP_HOME=$RUN/hadoop HADOOP_CONF_DIR=$RUN/conf JAVA_HOME=$J11
export PATH=$HADOOP_HOME/bin:$J11/bin:$PATH
if [ ! -d $RUN/conf ]; then
  log cp -r $HADOOP_HOME/etc/hadoop $RUN/conf
  cat >> $RUN/conf/hadoop-env.sh <<EOF
# stage-4 o8 (B3a)
export JAVA_HOME=$J11
export HADOOP_LOG_DIR=$RUN/logs
export HADOOP_PID_DIR=$RUN/pids
export HADOOP_HEAPSIZE_MAX=1g
export HDFS_NAMENODE_OPTS="-XX:+UseG1GC -Xms1g"
EOF
  cat > $RUN/conf/core-site.xml <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>fs.defaultFS</name><value>hdfs://localhost:29820</value></property>
  <property><name>hadoop.tmp.dir</name><value>$RUN/tmp</value></property>
  <property><name>ipc.server.max.response.size</name><value>1048576</value></property>
</configuration>
EOF
  cat > $RUN/conf/hdfs-site.xml <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>dfs.replication</name><value>1</value></property>
  <property><name>dfs.namenode.name.dir</name><value>$RUN/nn</value></property>
  <property><name>dfs.datanode.data.dir</name><value>$RUN/dn</value></property>
  <property><name>dfs.ls.limit</name><value>10000</value></property>
  <property><name>dfs.namenode.http-address</name><value>localhost:29870</value></property>
  <property><name>dfs.datanode.address</name><value>localhost:29866</value></property>
  <property><name>dfs.datanode.http.address</name><value>localhost:29864</value></property>
  <property><name>dfs.datanode.ipc.address</name><value>localhost:29867</value></property>
</configuration>
EOF
fi
java -version 2>&1; hadoop version | head -1
echo "== ports in use (must be none):"; ss -ltn | grep -E ':(29820|29870|29864|29866|29867)\b' && die "port busy"
free -g | head -2; df -h /mydata | tail -1

NNLOG() { ls $RUN/logs/hadoop-*-namenode-*.log 2>/dev/null | head -1; }
nnpid() { cat $RUN/pids/hadoop-*-namenode.pid 2>/dev/null; }
jmx() { curl -s 'http://localhost:29870/jmx?qry=Hadoop:service=NameNode,name=RpcActivityForPort29820' |
        python3 -I -c 'import json,sys; b=json.load(sys.stdin)["beans"][0]; print(b["SentBytes"], b["RpcProcessingTimeNumOps"], b["ReceivedBytes"])'; }
setk() { sed -i "s|<name>ipc.server.max.response.size</name><value>[0-9]*</value>|<name>ipc.server.max.response.size</name><value>$1</value>|" $RUN/conf/core-site.xml
         grep -o '<name>ipc.server.max.response.size</name><value>[0-9]*</value>' $RUN/conf/core-site.xml; }
warns() { local f; f=$(NNLOG); [ -n "$f" ] && grep -c 'Large response size' $f || echo 0; }

# ---- B3e 1-4: format, start ----
if [ ! -d $RUN/nn ]; then
  log hdfs namenode -format -force > $OUT/format.log 2>&1 || die "format failed"
  tail -3 $OUT/format.log
fi
log hdfs --daemon start namenode || die "nn start"
log hdfs --daemon start datanode || die "dn start"
log hdfs dfsadmin -safemode wait || die "safemode"

# ---- B3e 5: workload (B3c) ----
if ! hdfs dfs -test -d /big; then
  P=$(printf 'a%.0s' $(seq 195))
  echo "+ create /big (seq -w 0 9999 | sed ... | xargs -n 1000 hdfs dfs -mkdir -p)"; date
  seq -w 0 9999 | sed "s|^|/big/$P|" | xargs -n 1000 hdfs dfs -mkdir -p || die "mkdir"
  date
fi
hdfs dfs -count /big | tee $OUT/count-big.txt
hdfs dfs -ls /big | head -3 | cut -c1-120

# ---- B3e 6 (and 8): per K ----
runk() {  # $1 = K, $2 = label
  local K=$1 L=$2 W0 W1 S0 S1 n0 f
  echo "==== K=$K ($L) $(date)"
  setk $K
  log hdfs --daemon stop namenode; sleep 2
  log hdfs --daemon start namenode || die "nn restart"
  log hdfs dfsadmin -safemode wait || die "safemode"
  f=$(NNLOG); n0=$(wc -l < $f)
  grep -n 'ipc.server.max.response.size\|STARTUP_MSG: Starting NameNode' $f | tail -1 | cut -c1-120
  W0=$(warns); read S0 O0 RB0 < <(jmx)
  echo "before: warn=$W0 SentBytes=$S0 NumOps=$O0"
  local P=$(nnpid); echo "nn pid $P"
  log jcmd $P GC.run > /dev/null
  jcmd $P GC.heap_info > $OUT/heap-before-$L.txt; cat $OUT/heap-before-$L.txt
  log jcmd $P JFR.start name=r settings=profile filename=$RUN/jfr-$L.jfr
  for i in $(seq 20); do printf '%s ' "$(hdfs dfs -ls /big | wc -l)"; done | tee $OUT/lines-$L.txt; echo
  log jcmd $P JFR.stop name=r
  W1=$(warns); read S1 O1 RB1 < <(jmx)
  echo "after: warn=$W1 SentBytes=$S1 NumOps=$O1"
  echo "K=$K label=$L warn_new=$((W1-W0)) dSentBytes=$((S1-S0)) dNumOps=$((O1-O0)) dReceivedBytes=$((RB1-RB0))" | tee -a $OUT/summary.txt
  tail -n +$((n0+1)) $f | grep 'Large response size' | sed -E 's/.*Large response size ([0-9]+) for call (Call#[0-9]+ Retry#[0-9]+ )?([^ ]+).*/\1 \3/' |
     sort | uniq -c | tee $OUT/warn-lengths-$L.txt
  log jcmd $P GC.run > /dev/null
  jcmd $P GC.heap_info > $OUT/heap-after-$L.txt; cat $OUT/heap-after-$L.txt
  jcmd $P GC.class_histogram | grep -E '^ *num|\[B' | head -3 | tee $OUT/histo-after-$L.txt
  jfr print --json --events jdk.ObjectAllocationOutsideTLAB --stack-depth 6 $RUN/jfr-$L.jfr > $RUN/jfr-$L.json
  python3 -I $H/jfrsum.py $RUN/jfr-$L.json > $OUT/jfr-$L.txt
  grep -v '^setupResponse_alloc' $OUT/jfr-$L.txt
  grep '^setupResponse_alloc' $OUT/jfr-$L.txt | awk '{print $2,$3}' | sort | uniq -c | sort -rn | head -5
}
runk 1024 K1024
runk 1048576 K1048576
runk 67108864 K67108864

# ---- B3e 7: positive control at K = 64 MiB ----
echo "==== positive control $(date)"
for cap in 1048576 4194304; do
  echo "+ hdfs dfs -D ipc.maximum.response.length=$cap -ls /big"
  timeout 600 hdfs dfs -D ipc.maximum.response.length=$cap -ls /big > $OUT/pc-$cap.stdout 2> $OUT/pc-$cap.stderr
  echo "exit=$? lines=$(wc -l < $OUT/pc-$cap.stdout)" | tee -a $OUT/summary.txt
  grep -m3 -E 'exceeds maximum data length|Exception' $OUT/pc-$cap.stderr | cut -c1-250
done

# ---- B3e 8: repeat K = 1024 ----
runk 1024 K1024-repeat

# ---- B3e 9 / B4: cleanup ----
echo "==== cleanup $(date)"
log hdfs --daemon stop datanode
log hdfs --daemon stop namenode
sleep 3
echo "leftover:"; ps -eo pid,cmd | grep -E '[N]ameNode|[D]ataNode' | cut -c1-150 || echo none
du -sh $RUN/logs $RUN/jfr-* 2>/dev/null
echo "== done $(date)"
