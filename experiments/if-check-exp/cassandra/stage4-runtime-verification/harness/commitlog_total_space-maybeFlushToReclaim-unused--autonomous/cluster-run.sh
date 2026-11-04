#!/bin/bash
# Cluster tier (B3a-B3e, as amended 2026-10-21 R4) of commitlog_total_space-maybeFlushToReclaim-unused--autonomous.
# Usage: bash cluster-run.sh <outroot> <label> <capMiB> <throttled:1|0> [n]
#   labels: 256, 1024, 16384 (throttled, 32 threads, 20000/s), 256p (unthrottled probe, 128 threads)
# One node from ~/cassandra-cts, all state under RUN=/tmp/clcap (local /dev/sda3). Stops the node on any exit.
set -u
OUTROOT=${1:?}; ARM=${2:?}; CAP=${3:?}; THR=${4:?}; N=${5:-3000000}
CL=$HOME/cassandra-cts; RUN=/tmp/clcap; NODE=$RUN/node; O=$OUTROOT/$ARM
mkdir -p "$O"; LOG=$O/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
daemons() { ps -eo pid,cmd | grep '[j]ava.*CassandraDaemon' | awk '{print $1}'; }
SAMPLER=""; JMXS=""
stop_all() {
  [ -n "$SAMPLER" ] && kill $SAMPLER 2>/dev/null; [ -n "$JMXS" ] && kill $JMXS 2>/dev/null
  if [ -f $NODE/cassandra.pid ]; then
    P=$(cat $NODE/cassandra.pid); kill $P 2>/dev/null
    for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
    kill -0 $P 2>/dev/null && { log "kill -9 $P"; kill -9 $P; }
  fi
  log "daemons left: [$(daemons | tr '\n' ' ')]"
}
fail() { log "FAIL: $*"; stop_all; touch "$O/FAILED"; exit 1; }
trap 'stop_all' EXIT

log "cluster-run start arm=$ARM cap=${CAP}MiB throttled=$THR n=$N clone=$(git -C $CL rev-parse HEAD)"
[ -z "$(daemons)" ] || fail "a CassandraDaemon is already running"
ss -ltn | egrep -q ':(7000|7199|9042)\b' && fail "ports busy"
log "df: $(df -T /tmp | tail -1)"

# --- B3a configuration
rm -rf $NODE; mkdir -p $NODE/{data,commitlog,hints,saved_caches,cdc_raw,logs}
cp -r $CL/conf $NODE/conf
Y=$NODE/conf/cassandra.yaml
sed -i 's/^memtable_allocation_type:.*/memtable_allocation_type: offheap_objects/' $Y
grep -q '^commitlog_segment_size: 32MiB' $Y || fail "segment size line missing"
cat >> $Y <<EOF
data_file_directories:
    - $NODE/data
commitlog_directory: $NODE/commitlog
hints_directory: $NODE/hints
saved_caches_directory: $NODE/saved_caches
cdc_raw_directory: $NODE/cdc_raw
commitlog_total_space: ${CAP}MiB
memtable_heap_space: 4096MiB
memtable_offheap_space: 8192MiB
memtable_cleanup_threshold: 0.9
EOF
[ "$(grep -c '^commitlog_total_space' $Y)" = 1 ] || fail "commitlog_total_space count != 1"
diff $CL/conf/cassandra.yaml $Y > $O/yaml.diff

# --- B3e step 2: start
ulimit -n 100000
export MAX_HEAP_SIZE=16G CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$NODE/logs
log "+ bin/cassandra -p $NODE/cassandra.pid (ulimit -n $(ulimit -n))"
$CL/bin/cassandra -p $NODE/cassandra.pid > $NODE/logs/stdout.log 2>&1
ok=0
for i in $(seq 36); do
  sleep 5
  [ -n "$(daemons)" ] || fail "daemon died during start"
  if $CL/bin/nodetool status 2>/dev/null | grep -q '^UN' && [ "$($CL/bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
done
[ $ok = 1 ] || fail "node not UN/running within 180 s"
log "node up pid=$(cat $NODE/cassandra.pid)"
grep -o 'commitlog_total_space=[^;]*' $NODE/logs/system.log | head -1 | sed 's/^/CONFIG /' | tee -a "$LOG"
grep -o 'memtable_offheap_space=[^;]*\|memtable_heap_space=[^;]*\|memtable_allocation_type=[^;]*\|commitlog_segment_size=[^;]*\|memtable_cleanup_threshold=[^;]*' $NODE/logs/system.log | head -6 | sed 's/^/CONFIG /' | tee -a "$LOG"
SYSOFF=$(stat -c %s $NODE/logs/system.log)

# --- step 3: samplers (1 s du; 10 s JMX gauge, optional)
( while :; do echo "$(date +%s%3N),$(du -sb $NODE/commitlog|cut -f1),$(du -sk $NODE/commitlog|cut -f1),$(ls $NODE/commitlog|wc -l),$(du -sb $NODE/data|cut -f1)"; sleep 1; done ) > $O/du.csv &
SAMPLER=$!
( while :; do v=$($CL/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize -mg -f Value 2>&1 | tail -1); echo "$(date +%s%3N),$v"; sleep 10; done ) > $O/jmx.csv &
JMXS=$!
log "samplers $SAMPLER $JMXS"

# --- step 4: workload
if [ "$THR" = 1 ]; then RATE="threads=32 throttle=20000/s"; else RATE="threads=128"; fi
T0=$(date +%s%3N); log "STRESS_START $T0 rate=[$RATE]"
$CL/tools/bin/cassandra-stress write n=$N no-warmup cl=ONE -col 'n=FIXED(1)' 'size=FIXED(1024)' \
  -schema 'replication(factor=1)' -rate $RATE -node 127.0.0.1 -log file=$O/stress.log > $O/stress.out 2>&1
rc=$?; T1=$(date +%s%3N); log "STRESS_END $T1 rc=$rc ($(( (T1-T0)/1000 )) s)"
grep -E 'Op rate|Partition rate|Row rate|Total partitions|Total errors|Total operation time|END|FAILURE' $O/stress.out | head -20 | tee -a "$LOG"

# --- step 5: settle 60 s
sleep 60; TS=$(date +%s%3N); log "SETTLE_END $TS"
kill $SAMPLER $JMXS; SAMPLER=""; JMXS=""

# --- step 6: flush counts (this lifetime's system.log only, up to settle end)
tail -c +$((SYSOFF+1)) $NODE/logs/system.log > $O/system-run.log
grep 'Enqueuing flush of' $O/system-run.log > $O/flushes.txt
{ echo "COMMITLOG_DIRTY_standard1 $(grep -c 'keyspace1.standard1, Reason: COMMITLOG_DIRTY' $O/flushes.txt)"
  echo "MEMTABLE_LIMIT_standard1 $(grep -c 'keyspace1.standard1, Reason: MEMTABLE_LIMIT' $O/flushes.txt)"
  grep -oE 'Enqueuing flush of [^,]+, Reason: [A-Z_]+' $O/flushes.txt | sort | uniq -c | sed 's/^/REASON /'
  echo "ERRORS $(grep -c '^ERROR' $O/system-run.log)"
  echo "WARN_lines $(grep -c '^WARN' $O/system-run.log)"
} > $O/counts.txt
cat $O/counts.txt | tee -a "$LOG"
echo "T0=$T0 T1=$T1 TS=$TS CAP=$CAP THR=$THR N=$N" > $O/times.txt

# --- step 7: stop
stop_all; trap - EXIT
[ -z "$(daemons)" ] || log "WARNING daemon still present"
# --- step 8: keep logs, wipe node
cp $NODE/logs/system.log $NODE/logs/debug.log $NODE/logs/gc.log* $O/ 2>/dev/null
gzip -f $O/debug.log $O/stress.log 2>/dev/null
rm -rf $NODE
log "cluster-run end arm=$ARM"
touch "$O/DONE"
