#!/bin/bash
# Cluster tier (B3e) of memtable_heap_space-needsCleaning-nextClean--autonomous, one run.
# Usage: bash cluster-run.sh <R> <L MiB> [<t>]   e.g. bash cluster-run.sh R1 128 ; bash cluster-run.sh R4 512 0.15
# Environment deviations (shared host pc07): node on 127.0.0.5, JMX 7205, paths under ~/stage4-ncl and ~/stage4-logs/ncl.
# Amendments applied (case file, 2026-10-21): K1 Byteman ncl.btm (O1b, O7, O5b); K3 live-set sampler every 15 s;
# K4 N_flush counted for keyspace1.standard1 only.
set -u
R=$1; L=$2; T=${3:-}
C=$HOME/cassandra-ncl; H=$HOME/stage4-harness-run/ncl; W=$HOME/stage4-ncl; LOG=$HOME/stage4-logs/ncl/$R
ADDR=127.0.0.5; JMXP=7205
rm -rf $LOG; mkdir -p $LOG
exec > >(tee -a $LOG/run.log) 2>&1
NT="$C/bin/nodetool -p $JMXP"
mypids() { ps -eo pid,args | grep '[j]ava' | grep 'cassandra-ncl' | grep CassandraDaemon | awk '{print $1}'; }
PID=""; SAMPLERS=""
cleanup() {
  touch $W/stop
  if [ -n "$(mypids)" ]; then
    echo "== stopping node"; $NT stopdaemon >/dev/null 2>&1
    for i in $(seq 1 30); do [ -z "$(mypids)" ] && break; sleep 1; done
    for p in $(mypids); do kill $p; done; sleep 5; for p in $(mypids); do kill -9 $p; done
  fi
  for p in $(ps -eo pid,args | grep '[j]ava' | grep cassandra-ncl | grep -i stress | awk '{print $1}'); do kill $p; done
  [ -n "${SAMPLERS:-}" ] && wait $SAMPLERS 2>/dev/null   # not a bare wait: it would wait for the tee process substitution forever (harness fix 2026-10-21)
  echo "leftover cassandra-ncl java: $(ps -eo pid,args | grep '[j]ava' | grep -c cassandra-ncl)"
}
trap cleanup EXIT
trap "exit 1" INT TERM
fail() { echo "FAIL: $*"; exit 1; }
echo "== $(date -Is) $R L=${L}MiB t=${T:-unset(1/3)}"
[ -n "$(mypids)" ] && fail "a cassandra-ncl node is already running"
ss -ltn | grep -E "$ADDR:(7000|9042)\b|127.0.0.1:$JMXP\b" && fail "port in use"
df -h $HOME | tail -1
export CASSANDRA_CONF=$W/conf CASSANDRA_LOG_DIR=$LOG/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M
rm -rf $W/{data,commitlog,saved_caches,hints,cdc_raw,conf,stop}; mkdir -p $W; cp -r $C/conf $W/conf
Y=$W/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 's3mhs'|" \
  -e "s|^# data_file_directories:.*|data_file_directories: [$W/data]|" \
  -e "s|^# commitlog_directory:.*|commitlog_directory: $W/commitlog|" \
  -e "s|^# saved_caches_directory:.*|saved_caches_directory: $W/saved_caches|" \
  -e "s|^# hints_directory:.*|hints_directory: $W/hints|" \
  -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $W/cdc_raw|" \
  -e "s|^# commitlog_total_space:.*|commitlog_total_space: 4096MiB|" \
  -e "s|^# memtable_flush_writers:.*|memtable_flush_writers: 2|" \
  -e "s|^# memtable_heap_space:.*|memtable_heap_space: ${L}MiB|" \
  -e "s|^listen_address:.*|listen_address: $ADDR|" \
  -e "s|^rpc_address:.*|rpc_address: $ADDR|" \
  -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"$ADDR:7000\"|" $Y
[ -n "$T" ] && sed -i "s|^# memtable_cleanup_threshold: 0.11|memtable_cleanup_threshold: $T|" $Y
sed -i "s|^JMX_PORT=\"7199\"|JMX_PORT=\"$JMXP\"|" $W/conf/cassandra-env.sh
diff <(git -C $C show HEAD:conf/cassandra.yaml) $Y > $LOG/yaml.diff
cat $LOG/yaml.diff; grep -n '^JMX_PORT' $W/conf/cassandra-env.sh
ulimit -n 100000
BM=$C/build/lib/jars/byteman-4.0.20.jar
date +%s%3N > $LOG/t-start-node
JVM_EXTRA_OPTS="-javaagent:$BM=script:$H/ncl.btm -Dorg.jboss.byteman.compile.to.bytecode=true -Dncl.trace=$LOG/bm-all.txt" \
  $C/bin/cassandra -p $W/cassandra.pid > $LOG/out.log 2>&1
for i in $(seq 1 120); do
  [ -z "$(mypids)" ] && { sleep 2; [ -z "$(mypids)" ] && fail "daemon died during start"; }
  $NT status 2>/dev/null | grep -q "^UN  $ADDR" && $NT statusbinary 2>/dev/null | grep -q running && break
  sleep 3
done
$NT statusbinary | grep -q running || fail "node not up"
PID=$(cat $W/cassandra.pid); echo "PID=$PID"
grep 'Global memtable on-heap threshold' $LOG/logs/system.log || fail "no threshold line"
echo "deprecation lines: $(grep -c 'memtable_cleanup_threshold has been deprecated' $LOG/logs/system.log)"
echo "out.log lines mentioning byteman/rule errors: $(grep -ciE 'byteman|ERROR : Rule' $LOG/out.log)"
ST=$C/tools/bin/cassandra-stress
# harness fix 2026-10-21 (attempt 1 of R1 failed with "Cannot connect" 1 s after "Startup complete"): wait 10 s, retry up to 5 times
sleep 10; ok=0
for a in 1 2 3 4 5; do
  $ST write n=1000 cl=ONE -col 'n=FIXED(1)' 'size=FIXED(1024)' -schema 'replication(strategy=SimpleStrategy,factor=1)' -node $ADDR -port jmx=$JMXP > $LOG/stress-warmup.log 2>&1 && { ok=1; break; }
  echo "warm-up attempt $a failed: $(grep -m1 -o 'Cannot connect\|Exception[^:]*' $LOG/stress-warmup.log)"; sleep 10
done
[ $ok = 1 ] || fail "warm-up stress"
grep -E 'Total partitions|Total errors' $LOG/stress-warmup.log
$NT flush
LOGOFF=$(wc -c < $LOG/logs/system.log); OUTOFF=$(wc -c < $LOG/out.log); echo "system.log offset $LOGOFF, out.log offset $OUTOFF"
echo $LOGOFF > $LOG/syslog-offset; echo $OUTOFF > $LOG/out-offset
for i in 1 2 3; do echo "$(date +%s) $(jcmd $PID GC.class_histogram | tail -1)" >> $LOG/base.txt; sleep 30; done
cat $LOG/base.txt
rm -f $W/stop
( while kill -0 $PID 2>/dev/null && [ ! -f $W/stop ]; do
    echo "$(date +%s%3N) $($NT sjk mx -b org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize -mg -f Value 2>/dev/null | tail -1)"; sleep 1; done ) > $LOG/pool.txt &
SAMPLERS="$!"
( while kill -0 $PID 2>/dev/null && [ ! -f $W/stop ]; do
    echo "$(date +%s%3N) $(jcmd $PID GC.class_histogram | tail -1)"; sleep 15; done ) > $LOG/live.txt &
SAMPLERS="$SAMPLERS $!"
date +%s%3N > $LOG/t-start-stress
$ST write n=3000000 cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(1024)' \
   -rate threads=16 'fixed=10000/s' -schema 'replication(strategy=SimpleStrategy,factor=1)' -node $ADDR -port jmx=$JMXP \
   -log file=$LOG/stress.log > $LOG/stress-console.log 2>&1
echo "stress rc=$?"; date +%s%3N > $LOG/t-end-stress
grep -E 'Op rate|Total partitions|Total errors|Total operation time' $LOG/stress-console.log
sleep 30; touch $W/stop; sleep 16
tail -c +$((LOGOFF+1)) $LOG/logs/system.log > $LOG/system-run.log
grep 'Flushing largest' $LOG/system-run.log > $LOG/trig.txt
echo "triggers(all tables): $(wc -l < $LOG/trig.txt)"
echo "N_flush keyspace1.standard1 MEMTABLE_LIMIT: $(grep -c 'Enqueuing flush of keyspace1.standard1, Reason: MEMTABLE_LIMIT' $LOG/system-run.log)"
echo "keyspace1 flushes other reasons: $(grep 'Enqueuing flush of keyspace1' $LOG/system-run.log | grep -vc MEMTABLE_LIMIT)"
grep 'Enqueuing flush of keyspace1' $LOG/system-run.log | grep -v MEMTABLE_LIMIT | head -3
echo "BlockedOnAllocation Count: $($NT sjk mx -b org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation -mg -f Count 2>/dev/null | tail -1)"
$NT tablestats keyspace1.standard1 > $LOG/tablestats.txt; grep -E 'Memtable switch count|SSTable count|Space used \(live\)' $LOG/tablestats.txt
awk -v t0=$(cat $LOG/t-start-stress) '{ if ($2 >= t0) print }' $LOG/bm-all.txt > $LOG/bm.txt; echo "byteman lines: $(wc -l < $LOG/bm.txt)"
echo "ERROR lines: $(grep -c '^ERROR' $LOG/logs/system.log)"
du -sh $W; df -h $HOME | tail -1
echo "== $(date -Is) $R done"
