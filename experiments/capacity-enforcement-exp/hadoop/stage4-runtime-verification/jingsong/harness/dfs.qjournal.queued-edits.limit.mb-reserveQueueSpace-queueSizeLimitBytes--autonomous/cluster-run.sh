#!/usr/bin/env bash
# Stage-4 cluster tier (B3 + A1, A4) for dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous.
# Pseudo-distributed on one node: 1 NN (non-HA, edits in qjournal) + 3 JNs. JN3 is SIGSTOPped during the benchmark.
# Usage (on the node): cluster-run.sh <R> <harness-dir> [labels...]   default labels: L1 L10 L64 L512 ctl64
# Every command and its output goes to <R>/cluster/logs/cluster-run.log. Readings: READING lines and <R>/cluster/logs/readings.csv.
set -uo pipefail
R=${1:?R}; HD=${2:?harness}; shift 2
LABELS=${*:-"L1 L10 L64 L512 ctl64"}
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export PATH=$JAVA_HOME/bin:$PATH
DIST=/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2
H=$R/hadoop; C=$R/cluster; LG=$C/logs; mkdir -p "$LG"
LOG=$LG/cluster-run.log
NNB='http://127.0.0.1:9870/jmx?qry=Hadoop:service=NameNode,name=IPCLoggerChannel-127.0.0.1-8489'
JNB='http://127.0.0.1:8480/jmx?qry=Hadoop:service=JournalNode,name=Journal-capjournal'
JX="python3 -I $HD/jmxtool.py"
log() { echo "$*" | tee -a "$LOG"; }
run() { echo "+ $*" | tee -a "$LOG"; "$@" 2>&1 | tee -a "$LOG"; return ${PIPESTATUS[0]}; }
die() { log "STOP: $*"; exit 1; }
nnpid() { cat $C/pids/nn/hadoop-*-namenode.pid 2>/dev/null; }
jnpid() { cat $C/pids/jn$1/hadoop-*-journalnode.pid 2>/dev/null; }

log "=== cluster-run start $(date -Is) host=$(hostname) labels=$LABELS"
run md5sum "$HD/cluster-run.sh" "$HD/jmxtool.py"
run java -version
run free -g
run bash -c "ss -ltn | grep -E ':(9000|9870|848[0-9])\b' || echo 'ports free'"

prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
site() { echo '<?xml version="1.0"?>'; echo '<configuration>'; cat; echo '</configuration>'; }

setup() {
  [ -d "$H" ] || run cp -a "$DIST" "$H" || die "copy dist"
  mkdir -p $C/nn/name $C/jn1 $C/jn2 $C/jn3 $C/tmp
  local ports=("" "8485 8480 8481" "8487 8482 8483" "8489 8484 8486")
  for role in nn jn1 jn2 jn3; do
    rm -rf $C/conf-$role; cp -r $H/etc/hadoop $C/conf-$role
    mkdir -p $LG/$role $C/pids/$role
    { echo "export JAVA_HOME=$JAVA_HOME"; echo "export HADOOP_LOG_DIR=$LG/$role"; echo "export HADOOP_PID_DIR=$C/pids/$role"; } >> $C/conf-$role/hadoop-env.sh
    { prop fs.defaultFS hdfs://127.0.0.1:9000; prop hadoop.tmp.dir $C/tmp
      [ $role = nn ] && prop ipc.client.rpc-timeout.ms 0; } | site > $C/conf-$role/core-site.xml
  done
  echo 'export HDFS_NAMENODE_OPTS="-Xms2g -Xmx2g -XX:+UseG1GC"' >> $C/conf-nn/hadoop-env.sh
  for k in 1 2 3; do
    echo 'export HDFS_JOURNALNODE_OPTS="-Xmx512m"' >> $C/conf-jn$k/hadoop-env.sh
    set -- ${ports[$k]}
    { prop dfs.journalnode.rpc-address 127.0.0.1:$1; prop dfs.journalnode.http-address 127.0.0.1:$2
      prop dfs.journalnode.https-address 127.0.0.1:$3; prop dfs.journalnode.edits.dir $C/jn$k; } | site > $C/conf-jn$k/hdfs-site.xml
  done
  nnsite ""
}
nnsite() {  # $1 = L, empty = unset (default 10)
  { prop dfs.namenode.name.dir file://$C/nn/name
    prop dfs.namenode.edits.dir 'qjournal://127.0.0.1:8485;127.0.0.1:8487;127.0.0.1:8489/capjournal'
    prop dfs.namenode.edit.log.autoroll.multiplier.threshold 100
    prop dfs.namenode.safemode.extension 0
    prop dfs.replication 1
    prop dfs.namenode.http-address 127.0.0.1:9870
    [ -n "$1" ] && prop dfs.qjournal.queued-edits.limit.mb "$1"; } | site > $C/conf-nn/hdfs-site.xml
}

snap() {  # label point
  local pid; pid=$(nnpid)
  jmap -histo:live "$pid" > $LG/histo-$1-$2.txt 2>&1
  jcmd "$pid" GC.heap_info > $LG/heapinfo-$1-$2.txt 2>&1
  local b; b=$(awk '$4=="[B"{print $3","$2}' $LG/histo-$1-$2.txt)
  local tot; tot=$(awk '$1=="Total"{print $3}' $LG/histo-$1-$2.txt)
  echo "SNAP,$1,$2,byteArrayBytes_instances=$b,histoTotal=$tot" | tee -a "$LOG" >&2
  echo "$b"
}

wait_nn() {
  for i in $(seq 1 120); do
    $H/bin/hdfs --config $C/conf-nn dfsadmin -fs hdfs://127.0.0.1:9000 -safemode get >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

cleanup_all() {
  log "--- cleanup $(date -Is)"
  for k in 1 2 3; do p=$(jnpid $k); [ -n "$p" ] && kill -CONT "$p" 2>/dev/null; done
  touch $C/sampler.stop
  run $H/bin/hdfs --config $C/conf-nn --daemon stop namenode
  for k in 1 2 3; do run $H/bin/hdfs --config $C/conf-jn$k --daemon stop journalnode; done
  pkill -u "$(id -u)" -f '[N]NThroughputBenchmark' 2>/dev/null
  sleep 3
  run bash -c "ps -eo pid,cmd | grep -E '[N]ameNode|[J]ournalNode|[N]NThroughputBenchmark|[j]mxtool' || echo 'no daemons left'"
}
trap cleanup_all EXIT

setup
for k in 1 2 3; do run $H/bin/hdfs --config $C/conf-jn$k --daemon start journalnode; done
sleep 5
run jps
if [ ! -d $C/nn/name/current ]; then
  run $H/bin/hdfs --config $C/conf-nn namenode -format -force -nonInteractive || die "format"
fi
CP=$H/share/hadoop/hdfs/hadoop-hdfs-3.4.2-tests.jar:$H/share/hadoop/common/hadoop-common-3.4.2-tests.jar
[ -n "${EXTRA_CP:-}" ] && CP=$CP:$EXTRA_CP
log "HADOOP_CLASSPATH=$CP"
[ -f $LG/readings.csv ] || echo "label,L,stopped,W_bytesWritten,W_file,plateau_max,queued_at_b,outofsync_at_b,refusals,bytearr_a,bytearr_b,bytearr_c,drain_s,bench_rc,bench_s,outofsync_end" > $LG/readings.csv

for label in $LABELS; do
  case $label in L1) L=1; STOP=1;; L10) L=""; STOP=1;; L64) L=64; STOP=1;; L512) L=512; STOP=1;; ctl64) L=64; STOP=0;; *) die "label $label";; esac
  log "=== run $label (L='${L:-unset}', stop=$STOP) $(date -Is)"
  nnsite "$L"; run grep -c queued-edits $C/conf-nn/hdfs-site.xml
  run $H/bin/hdfs --config $C/conf-nn --daemon start namenode
  wait_nn || die "NN not up"
  run $H/bin/hdfs --config $C/conf-nn dfsadmin -fs hdfs://127.0.0.1:9000 -safemode leave
  run $H/bin/hdfs --config $C/conf-nn dfs -fs hdfs://127.0.0.1:9000 -mkdir -p /warm/$label
  sleep 3
  curl -s "$NNB" > $LG/bean-$label-start.json; run cat $LG/bean-$label-start.json
  run bash -c "curl -s 'http://127.0.0.1:9870/jmx?qry=Hadoop:service=NameNode,name=IPCLoggerChannel*' | grep -o '\"name\" : \"[^\"]*\"'"
  run grep -h "queueSizeLimit\|queued-edits" $LG/nn/*namenode*.log
  A=$(snap $label a)
  NNLOG=$(ls $LG/nn/hadoop-*-namenode-*.log); OFF=$(wc -l < $NNLOG)
  B0=$($JX get "$JNB" BytesWritten)
  INP=$(ls -t $C/jn1/capjournal/current/edits_inprogress_* | head -1); F0=$(stat -c %s $INP)
  log "W0: jn1 BytesWritten=$B0 inprogress=$INP size=$F0"
  rm -f $C/sampler.stop; : > $LG/jmx-$label.csv
  $JX sample $LG/jmx-$label.csv "$NNB" "$JNB" $C/sampler.stop & SPID=$!
  sleep 2
  if [ $STOP = 1 ]; then J3=$(jnpid 3); run kill -STOP $J3; log "STOPPED jn3 pid=$J3 at $(date +%s%3N)"; fi
  T0=$(date +%s)
  HADOOP_CLASSPATH=$CP HADOOP_CLIENT_OPTS="-Xmx2g" timeout 1200 $H/bin/hadoop --config $C/conf-nn \
     org.apache.hadoop.hdfs.server.namenode.NNThroughputBenchmark -fs hdfs://127.0.0.1:9000 \
     -op mkdirs -threads 16 -dirs ${DIRS:-1000000} -dirsPerDir 128 -baseDirName /bench$label > $LG/bench-$label.log 2>&1
  RC=$?; BS=$(( $(date +%s) - T0 ))
  log "BENCH $label rc=$RC seconds=$BS"; run tail -25 $LG/bench-$label.log
  sleep 10
  QB=$($JX get "$NNB" QueuedEditsSize); OB=$($JX get "$NNB" IsOutOfSync)
  Bb=$(snap $label b)
  B1=$($JX get "$JNB" BytesWritten); F1=$(stat -c %s $INP)
  REF=$(tail -n +$((OFF+1)) $NNLOG | grep -c "is going to exceed limit size")
  W=$(( B1 - B0 )); WF=$(( F1 - F0 ))
  log "AT_B $label QueuedEditsSize=$QB IsOutOfSync=$OB W_bytesWritten=$W W_file=$WF refusals=$REF"
  run bash -c "tail -n +$((OFF+1)) $NNLOG | grep -m3 'is going to exceed limit size'"
  T1=$(date +%s)
  if [ $STOP = 1 ]; then run kill -CONT $J3; log "CONTINUED jn3 at $(date +%s%3N)"; fi
  for i in $(seq 1 300); do q=$($JX get "$NNB" QueuedEditsSize); [ "$q" = 0 ] && break; sleep 2; done
  DR=$(( $(date +%s) - T1 )); log "DRAIN $label queued=$q after ${DR}s"
  sleep 5
  Cc=$(snap $label c)
  OE=$($JX get "$NNB" IsOutOfSync)
  touch $C/sampler.stop; wait $SPID
  PL=$(awk -F, 'NR>1 && $2 ~ /^[0-9]+$/ && $2>m {m=$2} END{print m+0}' $LG/jmx-$label.csv)
  echo "$label,${L:-unset},$STOP,$W,$WF,$PL,$QB,$OB,$REF,${A%%,*},${Bb%%,*},${Cc%%,*},$DR,$RC,$BS,$OE" | tee -a $LG/readings.csv | tee -a "$LOG"
  log "READING $label: plateau_max=$PL queued_at_b=$QB W=$W refusals=$REF bytearr a/b/c=${A%%,*}/${Bb%%,*}/${Cc%%,*}"
  run $H/bin/hdfs --config $C/conf-nn --daemon stop namenode
  sleep 3
  run bash -c "ps -eo pid,cmd | grep -E '[N]ameNode|[N]NThroughputBenchmark' || echo 'NN stopped'"
  [ "$RC" = 0 ] || die "benchmark rc=$RC in $label"
  [ "$q" = 0 ] || die "no drain in $label"
done
log "=== cluster-run end $(date -Is)"
