#!/bin/bash
# Cluster tier (B3a-B3e, as amended 2026-10-21 R4) of commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.
# Usage: bash cluster-run.sh <outroot> <capMiB> [n]
# One node from ~/cassandra-cl2; all node state under ~/stage4-cl2/node (local /dev/sda3), wiped before and after.
# Stops the node on any exit.
set -u
OUTROOT=${1:?}; CAP=${2:?}; N=${3:-1000000}
CL=$HOME/cassandra-cl2; NODE=$HOME/stage4-cl2/node; O=$OUTROOT/$CAP
mkdir -p "$O"; LOG=$O/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
daemons() { ps -eo pid,args | grep '[j]ava.*cassandra-cl2.*CassandraDaemon' | awk '{print $1}'; }
SAMPLER=""; JMXS=""
stop_all() {
  [ -n "$SAMPLER" ] && kill $SAMPLER 2>/dev/null; [ -n "$JMXS" ] && kill $JMXS 2>/dev/null
  SAMPLER=""; JMXS=""
  if [ -f $NODE/cassandra.pid ]; then
    P=$(cat $NODE/cassandra.pid)
    if kill -0 $P 2>/dev/null; then
      log "+ nodetool drain"; timeout 120 $CL/bin/nodetool drain >> "$LOG" 2>&1
      kill $P 2>/dev/null
      for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
      kill -0 $P 2>/dev/null && { log "kill -9 $P"; kill -9 $P; }
    fi
  fi
  log "daemons left: [$(daemons | tr '\n' ' ')]"
}
fail() { log "FAIL: $*"; stop_all; touch "$O/FAILED"; exit 1; }
trap 'stop_all' EXIT

log "cluster-run start cap=${CAP}MiB n=$N clone=$CL head=$(git -C $CL rev-parse HEAD)"
[ -z "$(daemons)" ] || fail "a cassandra-cl2 CassandraDaemon is already running"
ss -ltn | egrep -q ':(7000|7199|9042)\b' && fail "ports busy"
log "df: $(df -T $HOME | tail -1)"

# --- B3a configuration (R4)
rm -rf $NODE; mkdir -p $NODE/{data,commitlog,hints,saved_caches,cdc_raw,logs}
cp -r $CL/conf $NODE/conf
Y=$NODE/conf/cassandra.yaml
for kv in "cdc_enabled: false" "commitlog_sync: periodic" "commitlog_segment_size: 32MiB" "commitlog_disk_access_mode: legacy" "memtable_allocation_type: heap_buffers"; do
  grep -qx "$kv" $Y || fail "shipped yaml lacks '$kv'"
done
cat >> $Y <<EOF
data_file_directories:
    - $NODE/data
commitlog_directory: $NODE/commitlog
hints_directory: $NODE/hints
saved_caches_directory: $NODE/saved_caches
cdc_raw_directory: $NODE/cdc_raw
commitlog_total_space: ${CAP}MiB
memtable_heap_space: 8192MiB
memtable_cleanup_threshold: 0.9
EOF
for k in data_file_directories commitlog_directory hints_directory saved_caches_directory cdc_raw_directory commitlog_total_space \
         memtable_heap_space memtable_cleanup_threshold cdc_enabled commitlog_sync commitlog_segment_size commitlog_disk_access_mode; do
  [ "$(grep -c "^$k:" $Y)" = 1 ] || fail "key $k occurs $(grep -c "^$k:" $Y) times"
done
diff $CL/conf/cassandra.yaml $Y > $O/yaml.diff
grep -q '^archive_command=.\+' $CL/conf/commitlog_archiving.properties && fail "archive_command configured"

# --- B3e step 3: start
ulimit -n 100000
export MAX_HEAP_SIZE=24G HEAP_NEWSIZE=4G CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$NODE/logs
log "+ bin/cassandra -p $NODE/cassandra.pid (ulimit -n $(ulimit -n), MAX_HEAP_SIZE=$MAX_HEAP_SIZE)"
$CL/bin/cassandra -p $NODE/cassandra.pid > $NODE/logs/stdout.log 2>&1
ok=0
for i in $(seq 48); do
  sleep 5
  [ -n "$(daemons)" ] || fail "daemon died during start"
  if $CL/bin/nodetool status 2>/dev/null | grep -q '^UN' && [ "$($CL/bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
done
[ $ok = 1 ] || fail "node not UN/running within 240 s"
log "node up pid=$(cat $NODE/cassandra.pid)"
grep -oE '(commitlog_total_space|commitlog_segment_size|memtable_heap_space|memtable_cleanup_threshold|memtable_allocation_type|commitlog_disk_access_mode|cdc_enabled)=[^;]*' $NODE/logs/system.log | sort -u | sed 's/^/CONFIG /' | tee -a "$LOG"
grep -h 'commitlog_disk_access_mode resolved to' $NODE/logs/system.log | head -1 | tee -a "$LOG"

COL=(-col 'size=FIXED(1000)' 'n=FIXED(1)')
# --- step 4: schema-only baseline
log "+ cassandra-stress write n=1 (schema)"
$CL/tools/bin/cassandra-stress write n=1 cl=ONE "${COL[@]}" -rate threads=32 -mode native cql3 -node 127.0.0.1 > $O/stress-schema.out 2>&1 || fail "schema stress failed"
$CL/bin/nodetool flush >> "$LOG" 2>&1; sleep 10
log "baseline commitlog: $(du -sb $NODE/commitlog | cut -f1) B, $(ls $NODE/commitlog | wc -l) files"

# --- step 5: samplers. (ii)+(iii) every 0.25 s; (i) JMX back to back (R4)
( while :; do echo "$(date +%s%3N),$(du -sb --apparent-size $NODE/commitlog|cut -f1),$(ls $NODE/commitlog|grep -c '\.log$'),$(du -sb $NODE/data/keyspace1 2>/dev/null|cut -f1)"; sleep 0.25; done ) > $O/du.csv &
SAMPLER=$!
( while :; do v=$($CL/bin/nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize -f Value 2>&1 | tail -1); echo "$(date +%s%3N),$v"; done ) > $O/jmx.csv &
JMXS=$!
log "samplers du=$SAMPLER jmx=$JMXS"
sleep 3
T0=$(date +%s%3N); log "STRESS_START $T0"
$CL/tools/bin/cassandra-stress write n=$N cl=ONE "${COL[@]}" -rate threads=32 -mode native cql3 -node 127.0.0.1 \
  -log file=$O/stress.log > $O/stress.out 2>&1
rc=$?; T1=$(date +%s%3N); log "STRESS_END $T1 rc=$rc ($(( (T1-T0)/1000 )) s)"
grep -E 'Op rate|Partition rate|Row rate|Total partitions|Total errors|Total operation time|^END|FAILURE' $O/stress.out | head -20 | tee -a "$LOG"
log "tpstats MemtableFlushWriter: $($CL/bin/nodetool tpstats 2>/dev/null | grep MemtableFlushWriter)"
sleep 60; TS=$(date +%s%3N); log "SETTLE_END $TS"
log "tpstats MemtableFlushWriter: $($CL/bin/nodetool tpstats 2>/dev/null | grep MemtableFlushWriter)"
kill $SAMPLER $JMXS; SAMPLER=""; JMXS=""
echo "T0=$T0 T1=$T1 TS=$TS CAP=$CAP N=$N" > $O/times.txt

# --- step 6: census (this lifetime; flushes up to settle end are cut by time in the analysis)
cp $NODE/logs/system.log $O/system.log
grep 'Enqueuing flush of' $O/system.log > $O/flushes.txt
{ echo "COMMITLOG_DIRTY_standard1 $(grep -c 'keyspace1.standard1, Reason: COMMITLOG_DIRTY' $O/flushes.txt)"
  echo "MEMTABLE_LIMIT_standard1 $(grep -c 'keyspace1.standard1, Reason: MEMTABLE_LIMIT' $O/flushes.txt)"
  grep -oE 'Enqueuing flush of [^,]+, Reason: [A-Z_]+' $O/flushes.txt | sort | uniq -c | sed 's/^/REASON /'
  echo "ERRORS $(grep -c '^ERROR' $O/system.log)"
} > $O/counts.txt
cat $O/counts.txt | tee -a "$LOG"

# --- step 7: stop
stop_all; trap - EXIT
[ -z "$(daemons)" ] || log "WARNING daemon still present"
cp $NODE/logs/system.log $O/system-final.log; cp $NODE/logs/debug.log $O/debug.log 2>/dev/null; cp $NODE/logs/gc.log* $O/ 2>/dev/null
grep 'is no longer active and will be deleted' $O/debug.log > $O/segment-deletions.txt
gzip -f $O/debug.log $O/stress.log 2>/dev/null
rm -rf $NODE
log "cluster-run end cap=$CAP"
touch "$O/DONE"
