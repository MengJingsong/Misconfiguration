#!/usr/bin/env bash
# Stage-4 cluster tier (B3e, with amendments AM3-AM7) for
# dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous, order 20. Runs on the node.
# Usage: cluster-run.sh <K> <bytes|unset> <jn-in-progress true|false> <rounds> <jn-Xmx>
# Every command and its output goes to $C/cluster-run.log. Stops at the first failed setup step.
set -uo pipefail
K=$1; BYTES=$2; INPROG=$3; ROUNDS=$4; JNXMX=$5
R=/mydata/jingsong-s4/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity-run1
H=$R/hadoop
C=$R/cluster/$K
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$H/bin:$PATH
export HADOOP_HOME=$H
rm -rf $C; mkdir -p $C/out $C/data/{jn,nn1,nn2,tmp} $C/logs/{jn,nn1,nn2,client} $C/pid/{jn,nn1,nn2}
LOG=$C/cluster-run.log
run() { echo "+ [$(date -u +%FT%TZ)] $*" | tee -a $LOG; "$@" 2>&1 | tee -a $LOG; local rc=${PIPESTATUS[0]}; echo "rc=$rc" | tee -a $LOG; return $rc; }
die() { echo "FATAL: $*" | tee -a $LOG; stopall; exit 1; }

prop() { echo "  <property><name>$1</name><value>$2</value></property>"; }
mkconf() { # $1 dir, $2 nn id, $3 extra props (JN only)
  local d=$1; rm -rf $d; cp -r $H/etc/hadoop $d
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop fs.defaultFS hdfs://ns1; prop hadoop.tmp.dir $C/data/tmp; echo '</configuration>'; } > $d/core-site.xml
  { echo '<?xml version="1.0"?>'; echo '<configuration>'
    prop dfs.nameservices ns1; prop dfs.ha.namenodes.ns1 nn1,nn2; prop dfs.ha.namenode.id $2
    prop dfs.namenode.rpc-address.ns1.nn1 127.0.0.1:8020; prop dfs.namenode.rpc-address.ns1.nn2 127.0.0.1:8021
    prop dfs.namenode.http-address.ns1.nn1 127.0.0.1:9870; prop dfs.namenode.http-address.ns1.nn2 127.0.0.1:9871
    prop dfs.namenode.name.dir.ns1.nn1 $C/data/nn1; prop dfs.namenode.name.dir.ns1.nn2 $C/data/nn2
    prop dfs.namenode.shared.edits.dir qjournal://127.0.0.1:8485/ns1
    prop dfs.journalnode.edits.dir $C/data/jn
    prop dfs.journalnode.rpc-address 127.0.0.1:8485; prop dfs.journalnode.http-address 127.0.0.1:8480
    prop dfs.client.failover.proxy.provider.ns1 org.apache.hadoop.hdfs.server.namenode.ha.ConfiguredFailoverProxyProvider
    prop dfs.ha.fencing.methods 'shell(/bin/true)'
    prop dfs.ha.tail-edits.period 1s; prop dfs.ha.tail-edits.period.backoff-max 10s
    prop dfs.namenode.checkpoint.txns 10000000; prop dfs.permissions.enabled false
    prop dfs.namenode.edits.asynclogging false
    echo "$3"
    echo '</configuration>'; } > $d/hdfs-site.xml
}
stopall() {
  for d in nn2 nn1; do
    HADOOP_PID_DIR=$C/pid/$d HADOOP_LOG_DIR=$C/logs/$d hdfs --config $C/conf-$d --daemon stop namenode >>$LOG 2>&1
  done
  HADOOP_PID_DIR=$C/pid/jn HADOOP_LOG_DIR=$C/logs/jn hdfs --config $C/conf-jn --daemon stop journalnode >>$LOG 2>&1
  sleep 3
  ps -eo pid,cmd | grep -E "[N]ameNode|[J]ournalNode|[R]oundDriver" | grep -F "$R" | tee -a $LOG
}

echo "=== $K bytes=$BYTES jn-in-progress=$INPROG rounds=$ROUNDS jnXmx=$JNXMX host=$(hostname) $(date -u +%FT%TZ)" | tee -a $LOG
md5sum $R/harness/* | tee -a $LOG
mkconf $C/conf-nn1 nn1 "$(prop dfs.ha.tail-edits.in-progress true)"
mkconf $C/conf-nn2 nn2 "$(prop dfs.ha.tail-edits.in-progress true)"
JNX="$(prop dfs.ha.tail-edits.in-progress $INPROG)"
[ "$BYTES" != unset ] && JNX="$JNX
$(prop dfs.journalnode.edit-cache-size.bytes $BYTES)"
mkconf $C/conf-jn nn1 "$JNX"
run grep -E 'in-progress|edit-cache|asynclogging' $C/conf-jn/hdfs-site.xml $C/conf-nn2/hdfs-site.xml

start() { # $1 conf, $2 piddir, $3 daemon, $4 opts var
  run env HADOOP_PID_DIR=$C/pid/$2 HADOOP_LOG_DIR=$C/logs/$2 hdfs --config $C/conf-$1 --daemon start $3
}
export HDFS_JOURNALNODE_OPTS="-Xmx$JNXMX -XX:+UseParallelGC"
export HDFS_NAMENODE_OPTS="-Xmx2g"
start jn jn journalnode || die "jn start"
sleep 5
JNPID=$(cat $C/pid/jn/*journalnode.pid)
run hdfs --config $C/conf-nn1 namenode -format -clusterId s4ce -force -nonInteractive || die format
start nn1 nn1 namenode || die "nn1 start"
sleep 8
run hdfs --config $C/conf-nn2 namenode -bootstrapStandby -force -nonInteractive || die bootstrap
start nn2 nn2 namenode || die "nn2 start"
sleep 8
run hdfs --config $C/conf-nn1 haadmin -transitionToActive nn1 || die transition
run timeout 180 hdfs --config $C/conf-nn1 dfsadmin -fs hdfs://127.0.0.1:8020 -safemode wait || die safemode
run hdfs --config $C/conf-nn1 haadmin -getAllServiceState
grep -h "Enabling the journaled edits cache\|Cache capacity is set" $C/logs/jn/*.log | tee -a $LOG
# Defect D1 fix (2026-11-25): the baseline must be steady. Pre-baseline samples every 30 s (up to 10);
# the baseline is taken once two consecutive pre-samples' [B bytes agree within 1 MiB.
prev=""; for i in $(seq 1 10); do
  sleep 30
  python3 -I $R/harness/sample.py $K pre$i $JNPID $C/out >> $LOG 2>&1
  cur=$(tail -1 $C/out/readings.csv | cut -d, -f4)
  echo "pre$i [B=$cur" | tee -a $LOG
  if [ -n "$prev" ] && [ $(( cur > prev ? cur - prev : prev - cur )) -le 1048576 ]; then break; fi
  prev=$cur
done
run python3 -I $R/harness/sample.py $K baseline $JNPID $C/out
CP="$(hdfs --config $C/conf-nn1 classpath):$R/harness-classes"
done_r=0
while [ $done_r -lt $ROUNDS ]; do
  n=$(( ROUNDS - done_r < 10 ? ROUNDS - done_r : 10 ))
  java -Xmx512m -Dhadoop.log.dir=$C/logs/client -cp "$CP" RoundDriver $((done_r + 1)) $n >> $C/out/rounds.log 2>&1 \
    || { tail -5 $C/out/rounds.log | tee -a $LOG; die "rounds $((done_r+1))..$((done_r+n))"; }
  done_r=$((done_r + n))
  python3 -I $R/harness/sample.py $K r$done_r $JNPID $C/out >> $LOG 2>&1
  tail -1 $C/out/readings.csv | tee -a $LOG >/dev/null
  echo "[$(date -u +%FT%TZ)] rounds done: $done_r" | tee -a $LOG
done
sleep 30
run python3 -I $R/harness/sample.py $K final $JNPID $C/out
# AM10 (2026-11-25): heap-dump attribution of the cache (primary observable for K2-K6); hprof deleted afterwards
if [ "$K" != K0 ] && [ "$K" != K1 ]; then
  run /usr/lib/jvm/java-8-openjdk-amd64/bin/jcmd $JNPID GC.heap_dump $C/jn-heap.hprof
  python3 -I $R/harness/hprof_cache.py $C/jn-heap.hprof > $C/out/heap-attribution.txt 2>&1
  cat $C/out/heap-attribution.txt | tee -a $LOG
  rm -f $C/jn-heap.hprof
fi
# B3e step 8: correctness
run hdfs --config $C/conf-nn1 haadmin -getServiceState nn2
run curl -s "http://127.0.0.1:9871/jmx?qry=Hadoop:service=NameNode,name=NameNodeInfo" -o $C/out/nn2-nninfo.json
run curl -s "http://127.0.0.1:9870/jmx?qry=Hadoop:service=NameNode,name=NameNodeInfo" -o $C/out/nn1-nninfo.json
python3 -I -c "import json,sys
for f in ('$C/out/nn1-nninfo.json','$C/out/nn2-nninfo.json'):
    b=json.load(open(f))['beans'][0]; print(f.split('/')[-1], b.get('JournalTransactionInfo'))" | tee -a $LOG
python3 -I -c "import json; b=json.load(open('$C/out/histo/$K-final-jmx.json')); print('JN LastWrittenTxId', b.get('LastWrittenTxId'))" | tee -a $LOG
# logs: counts
echo "COUNT too-large WARN: $(grep -c 'A single batch of edits was too large' $C/logs/jn/*.log)" | tee -a $LOG
echo "COUNT out-of-sync: $(grep -c 'Edits cache is out of sync' $C/logs/jn/*.log)" | tee -a $LOG
echo "COUNT Initializing edits cache: $(grep -c 'Initializing edits cache' $C/logs/jn/*.log)" | tee -a $LOG
echo "COUNT nn2 fallback: $(grep -c 'falling back to streaming' $C/logs/nn2/*.log)" | tee -a $LOG
grep -m3 'A single batch of edits was too large' $C/logs/jn/*.log | cut -c1-400 > $C/out/too-large-first3.txt
grep -m3 'falling back to streaming' -A2 $C/logs/nn2/*.log | cut -c1-400 > $C/out/fallback-first3.txt
grep -h "Enabling the journaled edits cache\|Cache capacity is set" $C/logs/jn/*.log > $C/out/jn-capacity-line.txt
grep -E '^ROUND' $C/out/rounds.log | awk '{print $NF, $(NF-1)}' | sort | uniq -c | head -3 | tee -a $LOG
grep -c '^ROUND' $C/out/rounds.log | tee -a $LOG
run du -sb $C/data/jn $C/data/nn1
stopall
LEFT=$(ps -eo pid,cmd | grep -E "[N]ameNode|[J]ournalNode|[R]oundDriver" | grep -F "$R" | wc -l)
echo "LEFTOVER processes: $LEFT" | tee -a $LOG
# bulk data removed, logs kept (gzipped)
rm -rf $C/data
gzip -f $C/logs/*/*.log 2>/dev/null
echo "CLUSTER-DONE $K $(date -u +%FT%TZ)" | tee -a $LOG
