#!/bin/bash
# Cluster tier (B3, amendments 2026-10-26 R4-R6). Usage: bash cluster-run.sh <outroot> <arm: unset|128|256|8192> <rep> [n]
# One node from ~/s4-b8-cl at loopback 127.0.2.1 (port slot 2: JMX 7120). commitlog on the 4 GiB tmpfs ($VOL), everything
# else under /dev/shm/s4-b8-cl-node. Wipes both before and after. Stops the node on any exit; stops at the first failed check.
set -u
OUTROOT=${1:?}; ARM=${2:?}; REP=${3:?}; N=${4:-2200000}
TREE=$HOME/s4-b8-cl; VOL=$HOME/s4-b8-cl-vol; NODE=/dev/shm/s4-b8-cl-node; IP=127.0.2.1; JP=7120
O=$OUTROOT/$ARM-r$REP; mkdir -p "$O"; LOG=$O/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
daemons() { ps -eo pid,args | grep '[j]ava.*s4-b8-cl.*CassandraDaemon' | awk '{print $1}'; }
SAMPLER=""; JMXS=""; WD=""
stop_all() {
  for p in $SAMPLER $JMXS $WD; do kill $p 2>/dev/null; done; SAMPLER=""; JMXS=""; WD=""
  if [ -f $NODE/cassandra.pid ]; then
    P=$(cat $NODE/cassandra.pid)
    if kill -0 $P 2>/dev/null; then
      log "+ nodetool drain"; timeout 120 $TREE/bin/nodetool -p $JP drain >> "$LOG" 2>&1
      kill $P 2>/dev/null
      for i in $(seq 60); do kill -0 $P 2>/dev/null || break; sleep 1; done
      kill -0 $P 2>/dev/null && { log "kill -9 $P"; kill -9 $P; }
    fi
  fi
  log "daemons left: [$(daemons | tr '\n' ' ')]"
}
fail() { log "FAIL: $*"; stop_all; touch "$O/FAILED"; exit 1; }
trap 'stop_all' EXIT

case $ARM in unset) EXPECT=1024;; *) EXPECT=$ARM;; esac
log "cluster-run start arm=$ARM rep=$REP n=$N expected effective limit=${EXPECT}MiB head=$(git -C $TREE rev-parse HEAD)"
[ -z "$(daemons)" ] || fail "a s4-b8-cl CassandraDaemon is already running"
ss -ltn | egrep -q "(127.0.2.1|0.0.0.0|\*):(7000|9042)\b|:$JP\b" && fail "ports busy"
[ "$(df -B1M --output=size $VOL | tail -1 | tr -d ' ')" = 4096 ] || fail "$VOL is not the 4096 MiB tmpfs"
findmnt -n -o FSTYPE $VOL | grep -q tmpfs || fail "$VOL not tmpfs"

# --- B3a configuration (amendment R4)
rm -rf $NODE $VOL/commitlog; mkdir -p $NODE/{data,hints,saved_caches,cdc_raw,logs} $VOL/commitlog
cp -r $TREE/conf $NODE/conf
Y=$NODE/conf/cassandra.yaml
for kv in "cdc_enabled: false" "commitlog_sync: periodic" "commitlog_segment_size: 32MiB" "commitlog_disk_access_mode: legacy" "memtable_allocation_type: heap_buffers" "hinted_handoff_enabled: true" "listen_address: localhost" "rpc_address: localhost"; do
  grep -qx "$kv" $Y || fail "shipped yaml lacks '$kv'"
done
sed -i -e "s/^hinted_handoff_enabled: true/hinted_handoff_enabled: false/" -e "s/^listen_address: localhost/listen_address: $IP/" \
       -e "s/^rpc_address: localhost/rpc_address: $IP/" -e "s/- seeds: \"127.0.0.1:7000\"/- seeds: \"$IP:7000\"/" $Y
sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JP\"/" $NODE/conf/cassandra-env.sh
cat >> $Y <<EOF2
data_file_directories:
    - $NODE/data
commitlog_directory: $VOL/commitlog
hints_directory: $NODE/hints
saved_caches_directory: $NODE/saved_caches
cdc_raw_directory: $NODE/cdc_raw
memtable_heap_space: 8192MiB
memtable_cleanup_threshold: 0.9
EOF2
[ $ARM = unset ] || echo "commitlog_total_space: ${ARM}MiB" >> $Y
for k in data_file_directories commitlog_directory hints_directory saved_caches_directory cdc_raw_directory memtable_heap_space memtable_cleanup_threshold \
         cdc_enabled commitlog_sync commitlog_segment_size commitlog_disk_access_mode hinted_handoff_enabled listen_address rpc_address; do
  [ "$(grep -c "^$k:" $Y)" = 1 ] || fail "key $k occurs $(grep -c "^$k:" $Y) times"
done
want=1; [ $ARM = unset ] && want=0
[ "$(grep -c '^commitlog_total_space:' $Y)" = $want ] || fail "commitlog_total_space lines != $want"
grep -q "JMX_PORT=\"$JP\"" $NODE/conf/cassandra-env.sh || fail "JMX port not set"
diff $TREE/conf/cassandra.yaml $Y > $O/yaml.diff
grep -q '^archive_command=.\+' $TREE/conf/commitlog_archiving.properties && fail "archive_command configured"

# --- B3e step 2: start
ulimit -n 100000
export MAX_HEAP_SIZE=24G HEAP_NEWSIZE=4G CASSANDRA_CONF=$NODE/conf CASSANDRA_LOG_DIR=$NODE/logs
log "+ bin/cassandra -p $NODE/cassandra.pid (ulimit -n $(ulimit -n), MAX_HEAP_SIZE=$MAX_HEAP_SIZE)"
$TREE/bin/cassandra -p $NODE/cassandra.pid > $NODE/logs/stdout.log 2>&1
ok=0
for i in $(seq 48); do
  sleep 5
  [ -n "$(daemons)" ] || fail "daemon died during start"
  if $TREE/bin/nodetool -p $JP status 2>/dev/null | grep -q '^UN' && [ "$($TREE/bin/nodetool -p $JP statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
done
[ $ok = 1 ] || fail "node not UN/running within 240 s"
log "node up pid=$(cat $NODE/cassandra.pid)"
grep -oE '(commitlog_total_space|commitlog_segment_size|memtable_heap_space|memtable_cleanup_threshold|memtable_allocation_type|commitlog_disk_access_mode|cdc_enabled)=[^;]*' $NODE/logs/system.log | sort -u | sed 's/^/CONFIG /' | tee -a "$LOG"
grep -h 'Small commitlog volume detected' $NODE/logs/system.log | sed 's/^/WARNLINE /' | tee -a "$LOG" > $O/warnline.txt
# first-trigger check: the effective limit (EXPECTED)
# The startup config dump prints the yaml value (null when unset); the derived value is in the WARN line (shakedown 1 defect).
if [ $ARM = unset ]; then
  [ -s $O/warnline.txt ] || fail "unset arm: no 'Small commitlog volume detected' WARN"
  EFF="commitlog_total_space=$(sed -E 's/.*setting commitlog_total_space to ([0-9]+)\..*/\1/' $O/warnline.txt | head -1)MiB (from the WARN line)"
else
  [ ! -s $O/warnline.txt ] || fail "explicit arm logged the Small-volume WARN"
  EFF=$(grep -oE 'commitlog_total_space=[^;,]*' $NODE/logs/system.log | head -1)
fi
log "EFFECTIVE $EFF (expected ${EXPECT}MiB)"
echo "$EFF" | grep -qE "commitlog_total_space=${EXPECT} ?MiB" || fail "effective commitlog_total_space != ${EXPECT}MiB: $EFF"

COL=(-col 'size=FIXED(1000)' 'n=FIXED(1)')
log "+ cassandra-stress write n=1 (schema)"
$TREE/tools/bin/cassandra-stress write n=1 cl=ONE "${COL[@]}" -rate threads=32 -mode native cql3 -node $IP > $O/stress-schema.out 2>&1 || fail "schema stress failed"
$TREE/bin/nodetool -p $JP flush >> "$LOG" 2>&1; sleep 10
log "baseline commitlog: $(du -sb --apparent-size $VOL/commitlog | cut -f1) B, $(ls $VOL/commitlog | wc -l) files"

# --- step 3: samplers (du 0.25 s; JMX back to back) and the volume watchdog (kill stress above 3.6 GiB of commit log)
( while :; do echo "$(date +%s%3N),$(du -sb --apparent-size $VOL/commitlog|cut -f1),$(ls $VOL/commitlog|grep -c '\.log$'),$(df -B1 --output=used $VOL|tail -1|tr -d ' '),$(du -sb $NODE/data/keyspace1 2>/dev/null|cut -f1)"; sleep 0.25; done ) > $O/du.csv &
SAMPLER=$!
( while :; do v=$($TREE/bin/nodetool -p $JP sjk mx -mg -b org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize -f Value 2>&1 | tail -1); echo "$(date +%s%3N),$v"; done ) > $O/jmx.csv &
JMXS=$!
( while :; do u=$(tail -1 $O/du.csv 2>/dev/null | cut -d, -f4); if [ -n "$u" ] && [ "${u:-0}" -gt 3865470566 ]; then echo "VOLUME_OVER_90PCT $u" >> $O/ABORT; pkill -f "[c]assandra-stress.*$IP" ; fi; sleep 1; done ) &
WD=$!
log "samplers du=$SAMPLER jmx=$JMXS watchdog=$WD"
sleep 3
T0=$(date +%s%3N); log "STRESS_START $T0"
$TREE/tools/bin/cassandra-stress write n=$N cl=ONE "${COL[@]}" -rate threads=64 -mode native cql3 -node $IP \
  -log file=$O/stress.log > $O/stress.out 2>&1
rc=$?; T1=$(date +%s%3N); log "STRESS_END $T1 rc=$rc ($(( (T1-T0)/1000 )) s)"
grep -E 'Op rate|Partition rate|Row rate|Total partitions|Total errors|Total operation time|^END|FAILURE' $O/stress.out | head -20 | tee -a "$LOG"
[ ! -f $O/ABORT ] || fail "volume watchdog fired: $(cat $O/ABORT)"
[ $rc = 0 ] || fail "stress rc=$rc"
log "tpstats MemtableFlushWriter: $($TREE/bin/nodetool -p $JP tpstats 2>/dev/null | grep MemtableFlushWriter)"
sleep 60; TS=$(date +%s%3N); log "SETTLE_END $TS"
kill $SAMPLER $JMXS $WD; SAMPLER=""; JMXS=""; WD=""
echo "T0=$T0 T1=$T1 TS=$TS ARM=$ARM EXPECT=$EXPECT N=$N" > $O/times.txt

# --- step 5: census
cp $NODE/logs/system.log $O/system.log
grep 'Enqueuing flush of' $O/system.log > $O/flushes.txt
{ echo "COMMITLOG_DIRTY_standard1 $(grep -c 'keyspace1.standard1, Reason: COMMITLOG_DIRTY' $O/flushes.txt)"
  echo "MEMTABLE_LIMIT_any $(grep -c 'Reason: MEMTABLE_LIMIT' $O/flushes.txt)"
  grep -oE 'Enqueuing flush of [^,]+, Reason: [A-Z_]+' $O/flushes.txt | sort | uniq -c | sed 's/^/REASON /'
  echo "ERRORS $(grep -c '^ERROR' $O/system.log)"
} > $O/counts.txt
tee -a "$LOG" < $O/counts.txt

# --- step 6: stop
stop_all; trap - EXIT
[ -z "$(daemons)" ] || log "WARNING daemon still present"
cp $NODE/logs/debug.log $O/debug.log 2>/dev/null; cp $NODE/logs/gc.log* $O/ 2>/dev/null
grep 'is no longer active and will be deleted' $O/debug.log > $O/segment-deletions.txt
gzip -f $O/debug.log $O/stress.log 2>/dev/null
rm -rf $NODE $VOL/commitlog
log "cluster-run end arm=$ARM rep=$REP"
touch "$O/DONE"
