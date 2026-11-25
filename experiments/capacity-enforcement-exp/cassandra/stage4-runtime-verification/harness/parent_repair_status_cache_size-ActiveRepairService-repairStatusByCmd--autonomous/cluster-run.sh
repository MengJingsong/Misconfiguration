#!/usr/bin/env bash
# Cluster tier (B3e as amended by S4-A1/A3/A5) of case o127. On pc82, one invocation at a time:
#   bash cluster-run.sh <label> "<JVM_EXTRA_OPTS>" [M] [batch]
# Paths are literal under /mydata/jingsong-cass-s4/o127; only the node whose PID this script recorded is signalled.
set -uo pipefail
SRC=/mydata/jingsong-cass-s4/o127/c509
RUN=/mydata/jingsong-cass-s4/o127/node
H=$(cd "$(dirname "$0")" && pwd)
LABEL=$1; OPTS=$2; M=${3:-30000}; B=${4:-500}
OUT=/mydata/jingsong-cass-s4/o127/cluster/$LABEL; mkdir -p "$OUT"
exec > >(tee -a "$OUT/session.txt") 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
NT="$SRC/bin/nodetool -h 127.0.0.1 -p 7199"
# D1 fix (shakedown 2026-11-25): getParentRepairStatus returns a Guava ImmutableList; the client needs Guava to deserialize it.
JD="java -cp $SRC/build/lib/jars/guava-32.0.1-jre.jar Drive.java"
export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/logs
stopnode() {
  [ -s $RUN/pid ] || return 0; local p; p=$(cat $RUN/pid)
  if [ -d /proc/$p ] && grep -q CassandraDaemon /proc/$p/cmdline 2>/dev/null; then
    log "kill $p"; kill $p; for i in $(seq 1 15); do [ -d /proc/$p ] || break; sleep 1; done
    [ -d /proc/$p ] && { log "kill -9 $p"; kill -9 $p; sleep 2; }
  fi
  [ -d /proc/$p ] && log "WARNING $p alive" || log "node $p gone"
  rm -f /mydata/jingsong-cass-s4/o127/node/pid
}
die() { log "FAIL: $*"; stopnode; exit 1; }
trap 'stopnode' EXIT
histo() {  # $1 = phase
  local P; P=$(cat $RUN/pid)
  $NT flush >/dev/null 2>&1; log "flush exit $?"   # S4-A6: memtables (size estimates) out of the reading
  jcmd $P GC.class_histogram > $OUT/hist-$1.txt 2>&1
  local tot ba ent noti
  tot=$(awk '/^Total/{print $3}' $OUT/hist-$1.txt); ba=$(awk '$4=="[B"{print $3; exit}' $OUT/hist-$1.txt)
  ent=$(awk '$4=="com.google.common.cache.LocalCache$StrongAccessWriteEntry"{print $2; exit}' $OUT/hist-$1.txt)
  noti=$(awk '$4 ~ /Notification$/ {n+=$2} END{print n+0}' $OUT/hist-$1.txt)
  jcmd $P GC.run > /dev/null 2>&1; jcmd $P GC.heap_info > $OUT/heapinfo-$1.txt 2>&1
  local used; used=$(grep -o 'used [0-9]*K' $OUT/heapinfo-$1.txt | head -1)
  log "SAMPLE $LABEL phase=$1 total=$tot byteArr=$ba sawEntries=${ent:-0} notifications=$noti heap_info_$used"
}
log "label=$LABEL opts=\"$OPTS\" M=$M batch=$B host=$(hostname) arch=$(uname -m)"
ps -eo cmd | grep '[C]assandraDaemon' && die "a CassandraDaemon is already running"
rm -rf /mydata/jingsong-cass-s4/o127/node/data /mydata/jingsong-cass-s4/o127/node/commitlog /mydata/jingsong-cass-s4/o127/node/hints \
       /mydata/jingsong-cass-s4/o127/node/saved_caches /mydata/jingsong-cass-s4/o127/node/cdc_raw /mydata/jingsong-cass-s4/o127/node/logs
mkdir -p $RUN/data $RUN/commitlog $RUN/hints $RUN/saved_caches $RUN/cdc_raw $RUN/logs
python3 $H/mkconf.py $SRC $RUN; awk '/o127 stage-4 settings/,0' $SRC/conf/cassandra.yaml; grep -E '^(num_tokens|listen_address|rpc_address|# allocate)' $SRC/conf/cassandra.yaml
ulimit -n 100000; log "ulimit -n $(ulimit -n)"
if ss -ltn | grep -E ':(7000|7199|9042)\b'; then die "ports busy"; fi; log "ports 7000/7199/9042 free"
log "start JVM_EXTRA_OPTS=\"$OPTS\" MAX_HEAP_SIZE=$MAX_HEAP_SIZE HEAP_NEWSIZE=$HEAP_NEWSIZE"
( cd $SRC && JVM_EXTRA_OPTS="$OPTS" setsid nohup bin/cassandra -p $RUN/pid </dev/null > $OUT/cassandra.out 2>&1 & )
for i in $(seq 1 30); do [ -s $RUN/pid ] && break; sleep 1; done; [ -s $RUN/pid ] || die "no pid"; P=$(cat $RUN/pid); log "pid $P"
for i in $(seq 1 300); do
  [ -d /proc/$P ] || die "daemon died during start"
  [ "$($NT statusbinary 2>/dev/null | tr -d '[:space:]')" = running ] && { log "statusbinary running"; break; }; sleep 2
done
$NT status 2>&1 | grep -E '^(UN|DN|UJ)' ; $NT status 2>&1 | grep -q '^UN' || die "not UN"
log "property check (B3e.3)"; grep -c parent_repair_status_cache_size $RUN/logs/system.log
ps -o args= -p $P | tr ' ' '\n' | grep -E 'parent_repair|Xmx|Xmn' | tee $OUT/jvm-args.txt
log "schema (B3c)"
$SRC/bin/cqlsh 127.0.0.1 -e "CREATE KEYSPACE o127 WITH replication = {'class':'NetworkTopologyStrategy','datacenter1':2}; CREATE TABLE o127.t (k int PRIMARY KEY, v int);" 2>&1 | tail -5
$SRC/bin/cqlsh 127.0.0.1 -e "DESCRIBE KEYSPACE o127" 2>&1 | grep -i replication
log "setlogginglevel org.apache.cassandra.repair WARN"; $NT setlogginglevel org.apache.cassandra.repair WARN
sleep 5; histo base
log "drive: $JD repair $M $B"
( cd $H && $JD repair $M $B ) > $OUT/drive.txt 2>&1; log "drive exit $?"
grep -E 'DRIVE issued=(500|5000|10000|15000|20000|25000|30000) |DRIVE done|Exception' $OUT/drive.txt | head -20
for i in $(seq 1 600); do
  r=$( cd $H && $JD pool 2>&1 ); echo "$r" | grep -q 'active=0 pending=0' && break; sleep 1
done; log "$r"; $NT tpstats | grep -E 'Pool Name|Repair-Task' | tee $OUT/tpstats.txt
LAST=$(awk '/DRIVE done/{for(i=1;i<=NF;i++) if($i ~ /^lastCmd=/){sub("lastCmd=","",$i); print $i}}' $OUT/drive.txt)
log "probe last cmd $LAST"; ( cd $H && $JD probe $LAST ) 2>&1 | tee $OUT/probe.txt
histo after
log "sleep 60"; sleep 60; histo after60
log "count 1 $M"; ( cd $H && $JD count 1 $M ) 2>&1 | tee $OUT/count.txt
$NT repair_admin list 2>&1 | head -5 > $OUT/repair_admin.txt; cat $OUT/repair_admin.txt
grep -c '^ERROR' $RUN/logs/system.log | sed 's/^/ERROR lines: /'; grep -c '^WARN' $RUN/logs/system.log | sed 's/^/WARN lines: /'
stopnode; trap - EXIT
cp $RUN/logs/system.log $OUT/system.log; du -sh $RUN/logs | sed 's/^/logs size /'
ps -eo cmd | grep '[C]assandraDaemon' && log "LEFTOVER CassandraDaemon" || log "no CassandraDaemon"
ps -eo cmd | grep '[D]rive.java' && log "LEFTOVER Drive" || log "no Drive"
log "RUN done $LABEL"
