#!/bin/bash
# Cluster tier (B3e) of memtable_heap_space-adjustMemtableSize-0--autonomous, one run.
# Usage: bash cluster-run.sh <R> <L MiB> <sai|plain>     e.g. bash cluster-run.sh R1 64 sai
# Environment deviations (shared host pc07, another agent's node on 127.0.0.4/.6): node on 127.0.0.5, JMX 7205;
# $WORK -> clone ~/cassandra-sai, data ~/stage4-sai/node, conf ~/stage4-sai/conf, logs ~/stage4-logs/sai/<R>.
# Audit amendments applied (case file, 2026-10-22): A-K2 segment_write_buffer_size 16MiB; A-K3 SaiPoll sampler every 2 s,
# histograms every 30 s, flush counts after the run offset for the run's own table.
set -u
R=$1; L=$2; KIND=$3
C=$HOME/cassandra-sai; H=$(cd "$(dirname "$0")" && pwd); W=$HOME/stage4-sai; LOG=$HOME/stage4-logs/sai/$R
ADDR=127.0.0.5; JMXP=7205
if [ $KIND = sai ]; then TBL=t_sai; IDX=t_sai_v_idx; PROF=$H/sai-profile.yaml; else TBL=t_plain; IDX=-; PROF=$H/plain-profile.yaml; fi
rm -rf $LOG; mkdir -p $LOG/hist
exec > >(tee -a $LOG/run.log) 2>&1
NT="$C/bin/nodetool -h 127.0.0.1 -p $JMXP"
ST=$C/tools/bin/cassandra-stress
mypids() { for p in $(pgrep -x java); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q 'cassandra-sai.*CassandraDaemon' && echo $p; done; }
mystress() { for p in $(pgrep -x java); do tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q 'cassandra-sai.*stress' && echo $p; done; }
SAMPLERS=""
cleanup() {
  touch $W/stop
  [ -n "${SAMPLERS:-}" ] && wait $SAMPLERS 2>/dev/null
  for p in $(mystress); do kill $p; done
  if [ -n "$(mypids)" ]; then
    echo "== stopping node"; $NT stopdaemon >/dev/null 2>&1
    for i in $(seq 1 60); do [ -z "$(mypids)" ] && break; sleep 1; done
    for p in $(mypids); do kill $p; done; sleep 5; for p in $(mypids); do kill -9 $p; done
  fi
  echo "leftover cassandra-sai java: daemon=[$(mypids)] stress=[$(mystress)]"
  echo "== $(date -Is) $R exit"
}
trap cleanup EXIT
trap "exit 1" INT TERM
fail() { echo "FAIL: $*"; exit 1; }
echo "== $(date -Is) $R L=${L}MiB kind=$KIND table=$TBL"
sha256sum $H/*
[ -n "$(mypids)" ] && fail "a cassandra-sai node is already running"
ss -ltn | grep -E "$ADDR:(7000|9042)\b|:$JMXP\b" && fail "port in use"
FREE=$(df -BG --output=avail $HOME | tail -1 | tr -dc 0-9); echo "free on / : ${FREE}G"; [ $FREE -lt 15 ] && fail "less than 15G free"
export CASSANDRA_CONF=$W/conf CASSANDRA_LOG_DIR=$LOG/logs MAX_HEAP_SIZE=4G
rm -rf $W/node $W/conf $W/stop $W/cassandra.pid; mkdir -p $W/node; cp -r $C/conf $W/conf
Y=$W/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 'saiexp'|" \
  -e "s|^# data_file_directories:.*|data_file_directories: [$W/node/data]|" \
  -e "s|^# commitlog_directory:.*|commitlog_directory: $W/node/commitlog|" \
  -e "s|^# saved_caches_directory:.*|saved_caches_directory: $W/node/saved_caches|" \
  -e "s|^# hints_directory:.*|hints_directory: $W/node/hints|" \
  -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $W/node/cdc_raw|" \
  -e "s|^# memtable_heap_space:.*|memtable_heap_space: ${L}MiB|" \
  -e "s|^memtable_allocation_type:.*|memtable_allocation_type: heap_buffers|" \
  -e "s|^# commitlog_total_space:.*|commitlog_total_space: 8192MiB|" \
  -e "s|^# concurrent_compactors:.*|concurrent_compactors: 2|" \
  -e "s|^# sai_options:|sai_options:|" \
  -e "s|^  # segment_write_buffer_size: 1024MiB|  segment_write_buffer_size: 16MiB|" \
  -e "s|^listen_address:.*|listen_address: $ADDR|" \
  -e "s|^rpc_address:.*|rpc_address: $ADDR|" \
  -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"$ADDR:7000\"|" $Y
sed -i "s|^JMX_PORT=\"7199\"|JMX_PORT=\"$JMXP\"|" $W/conf/cassandra-env.sh
diff <(git -C $C show HEAD:conf/cassandra.yaml) $Y > $LOG/yaml.diff
cat $LOG/yaml.diff; grep -n '^JMX_PORT' $W/conf/cassandra-env.sh
[ $(grep -c '^>' $LOG/yaml.diff) -eq 14 ] || fail "yaml edits incomplete"
ulimit -n 100000
date +%s%3N > $LOG/t-start-node
$C/bin/cassandra -p $W/cassandra.pid > $LOG/out.log 2>&1
for i in $(seq 1 100); do
  [ -z "$(mypids)" ] && { sleep 2; [ -z "$(mypids)" ] && fail "daemon died during start"; }
  $NT status 2>/dev/null | grep -q "^UN  $ADDR" && $NT statusbinary 2>/dev/null | grep -q running && break
  sleep 3
done
$NT statusbinary | grep -q running || fail "node not up"
PID=$(cat $W/cassandra.pid); echo "PID=$PID mypids=$(mypids)"
grep 'Global memtable on-heap threshold' $LOG/logs/system.log || fail "no threshold line"
grep -q "Global memtable on-heap threshold is enabled at ${L}MiB" $LOG/logs/system.log || fail "threshold is not ${L}MiB"
grep -E 'Xmx|Xms' $LOG/logs/system.log | head -1 | grep -oE -- '-Xm[sx][0-9]+[MGK]' | sort -u
sleep 10; ok=0
for a in 1 2 3 4 5; do
  $ST user profile=$PROF "ops(insert=1)" n=1 no-warmup cl=ONE -node $ADDR -port jmx=$JMXP > $LOG/stress-schema.log 2>&1 && { ok=1; break; }
  echo "schema attempt $a failed: $(grep -m1 -oE 'Cannot connect|Exception[^:]*' $LOG/stress-schema.log)"; sleep 10
done
[ $ok = 1 ] || fail "schema stress"
grep -E 'Total partitions|Total errors' $LOG/stress-schema.log
$NT flush saiks
echo "schema:"; $C/bin/cqlsh $ADDR -e "DESCRIBE KEYSPACE saiks" 2>&1 | grep -E 'CREATE (TABLE|INDEX|CUSTOM)'
sleep 20
jcmd $PID GC.class_histogram > $LOG/hist/H0.txt; echo "H0 $(tail -1 $LOG/hist/H0.txt)"
LOGOFF=$(wc -c < $LOG/logs/system.log); echo $LOGOFF > $LOG/syslog-offset; echo "system.log offset $LOGOFF"
rm -f $W/stop
java $H/SaiPoll.java $JMXP $TBL $IDX 2000 $W/stop > $LOG/samples.csv 2> $LOG/saipoll.err &
SAMPLERS="$!"
( while kill -0 $PID 2>/dev/null && [ ! -f $W/stop ]; do
    ts=$(date +%s%3N); jcmd $PID GC.class_histogram > $LOG/hist/h-$ts.txt 2>&1; echo "$ts $(tail -1 $LOG/hist/h-$ts.txt)"
    for i in $(seq 1 30); do [ -f $W/stop ] && break; sleep 1; done; done ) > $LOG/hist-index.txt &
SAMPLERS="$SAMPLERS $!"
sleep 3
date +%s%3N > $LOG/t-start-stress
$ST user profile=$PROF "ops(insert=1)" n=10000000 no-warmup cl=ONE -pop seq=1..10000000 -rate threads=64 \
   -node $ADDR -port jmx=$JMXP -log file=$LOG/stress.log > $LOG/stress-console.log 2>&1
echo "stress rc=$?"; date +%s%3N > $LOG/t-end-stress
grep -E 'Op rate|Total partitions|Total errors|Total operation time' $LOG/stress-console.log
ALIVE=1; [ -z "$(mypids)" ] && { ALIVE=0; echo "NODE DIED during stress"; }
# harness fix 2026-10-22 (R1 attempt 1): count 'OutOfMemoryError: ' only; the JVM flags (-XX:+HeapDumpOnOutOfMemoryError) matched the bare word
echo "OOM/crash evidence: $(grep -c 'OutOfMemoryError: ' $LOG/logs/system.log $LOG/out.log 2>/dev/null | tr '\n' ' ') hs_err: $(ls $C/hs_err* $W/hs_err* 2>/dev/null)"
if [ $ALIVE = 1 ]; then
  sleep 120
  $NT flush saiks
  ts=$(date +%s%3N); jcmd $PID GC.class_histogram > $LOG/hist/final-$ts.txt; echo "final $ts $(tail -1 $LOG/hist/final-$ts.txt)"
fi
touch $W/stop; wait $SAMPLERS 2>/dev/null; SAMPLERS=""
# system.log of the run (rolled zips first, then the current file), from the offset
( for z in $(ls $LOG/logs/system.log.*.zip 2>/dev/null | sort); do unzip -p $z; done; cat $LOG/logs/system.log ) > $LOG/system-all.log
tail -c +$((LOGOFF+1)) $LOG/system-all.log > $LOG/system-run.log
grep 'Flushing largest' $LOG/system-run.log > $LOG/trig.txt
grep "Enqueuing flush of saiks.$TBL" $LOG/system-run.log > $LOG/flushes.txt
echo "Flushing largest lines: $(wc -l < $LOG/trig.txt)"
echo "N_flush saiks.$TBL MEMTABLE_LIMIT: $(grep -c 'Reason: MEMTABLE_LIMIT' $LOG/flushes.txt)"
echo "saiks.$TBL flushes other reasons: $(grep -vc 'Reason: MEMTABLE_LIMIT' $LOG/flushes.txt)"; grep -v 'Reason: MEMTABLE_LIMIT' $LOG/flushes.txt | cut -c1-200 | head -5
echo "other tables' MEMTABLE_LIMIT flushes: $(grep 'Enqueuing flush of' $LOG/system-run.log | grep -v "saiks.$TBL" | grep -c MEMTABLE_LIMIT)"
if [ $ALIVE = 1 ]; then
  echo "BlockedOnAllocation Count: $($NT sjk mx -b org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation -mg -f Count 2>/dev/null | tail -1)"
  $NT tablestats saiks.$TBL > $LOG/tablestats.txt 2>&1; grep -E 'Memtable switch count|SSTable count|Space used \(live\)' $LOG/tablestats.txt
  $NT compactionstats > $LOG/compactionstats.txt 2>&1; head -3 $LOG/compactionstats.txt
fi
echo "ERROR lines: $(grep -c '^ERROR' $LOG/system-run.log)"; grep '^ERROR' $LOG/system-run.log | cut -c1-200 | head -3
echo "samples: $(wc -l < $LOG/samples.csv); histograms: $(ls $LOG/hist | wc -l); saipoll.err: $(wc -l < $LOG/saipoll.err)"
du -sh $W/node; df -h $HOME | tail -1
echo "== $(date -Is) $R done"
