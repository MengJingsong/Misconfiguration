#!/bin/bash
# Cluster tier (B3, as amended 2026-10-23 B2i.5) of commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.
# Usage: bash cluster-run.sh <outroot> <label> <S_MiB> <mode mmap|lz4> <total_MiB> <n> <load stress|loader|none>
# One node from $TREE; all node state under $NODE (local /dev/sda3), wiped before and after. Stops the node on any exit.
set -u
OUTROOT=${1:?}; LABEL=${2:?}; S=${3:?}; MODE=${4:?}; TOTAL=${5:?}; N=${6:?}; LOAD=${7:?}
TREE=${TREE:-$HOME/stage4-seg/treeB}; NODE=${NODE:-$HOME/stage4-seg/nodeB}; HARN=$(cd "$(dirname "$0")" && pwd)
SYNC=${SYNC:-10s}; HEAP=${HEAP:-2G}; MEMHEAP=${MEMHEAP:-1024MiB}; MEMOFF=${MEMOFF:-1024MiB}
O=$OUTROOT/$LABEL; mkdir -p "$O"; LOG=$O/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
daemons() { ps -eo pid,args | grep "[j]ava.*$TREE.*CassandraDaemon" | awk '{print $1}'; }
SAMPLER=""; JMXS=""
stop_all() {
  [ -n "$SAMPLER" ] && kill $SAMPLER 2>/dev/null; [ -n "$JMXS" ] && kill $JMXS 2>/dev/null
  SAMPLER=""; JMXS=""
  if [ -f $NODE/cassandra.pid ]; then
    P=$(cat $NODE/cassandra.pid)
    if kill -0 $P 2>/dev/null; then
      log "+ nodetool drain"; timeout 120 $TREE/bin/nodetool drain >> "$LOG" 2>&1
      kill $P 2>/dev/null
      for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
      kill -0 $P 2>/dev/null && { log "kill -9 $P"; kill -9 $P; }
    fi
  fi
  log "daemons left: [$(daemons | tr '\n' ' ')]"
}
fail() { log "FAIL: $*"; stop_all; touch "$O/FAILED"; exit 1; }
trap 'stop_all' EXIT

log "cluster-run start label=$LABEL S=${S}MiB mode=$MODE total=${TOTAL}MiB n=$N load=$LOAD sync=$SYNC heap=$HEAP tree=$TREE head=$(git -C $TREE rev-parse HEAD)"
[ -z "$(daemons)" ] || fail "a CassandraDaemon of this tree is already running"
ss -ltn | egrep -q ':(7000|7199|9042|9091)\b' && fail "ports busy"
log "df: $(df -T $HOME | tail -1)"

rm -rf $NODE; mkdir -p $NODE/{data,commitlog,hints,saved_caches,cdc_raw,logs}
cp -r $TREE/conf $NODE/conf
Y=$NODE/conf/cassandra.yaml
setkey() { # replace an existing uncommented key, or append
  if grep -q "^$1:" $Y; then sed -i "s|^$1:.*|$1: $2|" $Y; else echo "$1: $2" >> $Y; fi; }
setkey commitlog_segment_size ${S}MiB; setkey commitlog_total_space ${TOTAL}MiB; setkey commitlog_sync periodic; setkey commitlog_sync_period $SYNC
setkey commitlog_disk_access_mode legacy; setkey memtable_heap_space $MEMHEAP; setkey memtable_offheap_space $MEMOFF
setkey cdc_enabled false; setkey memtable_allocation_type heap_buffers
cat >> $Y <<EOT
data_file_directories:
    - $NODE/data
commitlog_directory: $NODE/commitlog
hints_directory: $NODE/hints
saved_caches_directory: $NODE/saved_caches
cdc_raw_directory: $NODE/cdc_raw
EOT
[ "$MODE" = lz4 ] && printf 'commitlog_compression:\n    - class_name: LZ4Compressor\n' >> $Y
for k in data_file_directories commitlog_directory hints_directory saved_caches_directory cdc_raw_directory commitlog_total_space memtable_heap_space \
         memtable_offheap_space cdc_enabled commitlog_sync commitlog_sync_period commitlog_segment_size commitlog_disk_access_mode memtable_allocation_type; do
  [ "$(grep -c "^$k:" $Y)" = 1 ] || fail "key $k occurs $(grep -c "^$k:" $Y) times"
done
[ "$MODE" = lz4 ] && { [ "$(grep -c '^commitlog_compression:' $Y)" = 1 ] || fail "compression key"; }
diff $TREE/conf/cassandra.yaml $Y > $O/yaml.diff
grep -q '^archive_command=.\+' $TREE/conf/commitlog_archiving.properties && fail "archive_command configured"

ulimit -n 100000
export MAX_HEAP_SIZE=$HEAP HEAP_NEWSIZE=800M CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$NODE/logs
log "+ bin/cassandra -p $NODE/cassandra.pid (ulimit -n $(ulimit -n), heap $HEAP)"
JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary" $TREE/bin/cassandra -p $NODE/cassandra.pid > $NODE/logs/stdout.log 2>&1
ok=0
for i in $(seq 48); do
  sleep 5
  [ -n "$(daemons)" ] || fail "daemon died during start"
  if $TREE/bin/nodetool status 2>/dev/null | grep -q '^UN' && [ "$($TREE/bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
done
[ $ok = 1 ] || fail "node not UN/running within 240 s"
PID=$(cat $NODE/cassandra.pid); log "node up pid=$PID"
grep -oE '(commitlog_total_space|commitlog_segment_size|memtable_heap_space|memtable_cleanup_threshold|memtable_allocation_type|commitlog_disk_access_mode|commitlog_sync_period|cdc_enabled)=[^;]*' $NODE/logs/system.log | sort -u | sed 's/^/CONFIG /' | tee -a "$LOG"
grep -h 'commitlog_disk_access_mode resolved to' $NODE/logs/system.log | head -1 | tee -a "$LOG"
grep -h 'CommitLog' $NODE/logs/system.log | grep -iE 'compress|segment' | head -3 | tee -a "$LOG"
sleep 10
log "idle baseline: $(ls -l $NODE/commitlog | grep '\.log' | awk '{print $9":"$5}' | tr '\n' ' ')"

if [ "$LOAD" = stress ]; then
  log "+ cassandra-stress write n=1 (schema)"
  $TREE/tools/bin/cassandra-stress write n=1 cl=ONE -col 'size=FIXED(1024)' 'n=FIXED(1)' -schema keyspace=ks1 'replication(factor=1)' -rate threads=4 -mode native cql3 -node 127.0.0.1 > $O/stress-schema.out 2>&1 || fail "schema stress failed"
fi
python3 -I $HARN/sampler.py $NODE/commitlog $NODE/cassandra.pid $O/ds 0.25 &
SAMPLER=$!
( while :; do v=$($TREE/bin/nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize -f Value 2>&1 | tail -1); echo "$(date +%s%3N),$v"; sleep 1; done ) > $O/jmx.csv &
JMXS=$!
log "samplers ds=$SAMPLER jmx=$JMXS"
sleep 3
T0=$(date +%s%3N); log "LOAD_START $T0"
case $LOAD in
  stress) $TREE/tools/bin/cassandra-stress write n=$N cl=ONE -col 'size=FIXED(1024)' 'n=FIXED(1)' -schema keyspace=ks1 'replication(factor=1)' -rate threads=64 -mode native cql3 -node 127.0.0.1 -log file=$O/stress.log > $O/stress.out 2>&1; rc=$?;;
  loader) ZIP=$(ls $TREE/lib/cassandra-driver-internal-only-*.zip | head -1); python3 -I $HARN/loader.py $ZIP $N 1000 > $O/loader.out 2>&1; rc=$?;;
  none) sleep 30; rc=0;;
esac
T1=$(date +%s%3N); log "LOAD_END $T1 rc=$rc ($(( (T1-T0)/1000 )) s)"
grep -E 'Op rate|Partition rate|Total partitions|Total errors|Total operation time|^END|FAILURE|LOADER_DONE' $O/stress.out $O/loader.out 2>/dev/null | head -20 | tee -a "$LOG"
jcmd $PID VM.native_memory summary > $O/nmt-after-load.txt 2>&1
$TREE/bin/nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=CommitLog,name=OversizedMutations -f Count > $O/oversized.txt 2>&1
sleep 30; TS=$(date +%s%3N); log "SETTLE_END $TS"
kill $SAMPLER $JMXS; wait $SAMPLER 2>/dev/null; SAMPLER=""; JMXS=""
echo "T0=$T0 T1=$T1 TS=$TS S=$S MODE=$MODE TOTAL=$TOTAL N=$N LOAD=$LOAD" > $O/times.txt
ls -l --time-style=full-iso $NODE/commitlog > $O/final-ls.txt
du -sb --apparent-size $NODE/commitlog > $O/final-du.txt
cp $NODE/logs/system.log $O/system.log
grep 'Enqueuing flush of' $O/system.log > $O/flushes.txt
{ grep -oE 'Enqueuing flush of [^,]+, Reason: [A-Z_]+' $O/flushes.txt | sort | uniq -c | sed 's/^/REASON /'
  echo "ERRORS $(grep -c '^ERROR' $O/system.log)"; } > $O/counts.txt
cat $O/counts.txt | tee -a "$LOG"
stop_all; trap - EXIT
[ -z "$(daemons)" ] || log "WARNING daemon still present"
cp $NODE/logs/system.log $O/system-final.log; cp $NODE/logs/debug.log $O/debug.log 2>/dev/null
grep -E 'is no longer active and will be deleted|Allocating new segment|Creating new commit log segment|CommitLog-' $O/debug.log > $O/segment-events.txt 2>/dev/null
gzip -f $O/debug.log $O/stress.log 2>/dev/null
rm -rf $NODE
log "cluster-run end label=$LABEL"
touch "$O/DONE"
