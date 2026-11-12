#!/usr/bin/env bash
# Cluster tier (B3e, with AM1-AM3) of ip_cache_max_size--autonomous, one K per call.
# Usage: bash cluster-run.sh <run-name> <K> [w1-n] [w2-m] [settle-s]
set -euo pipefail
WORK=/mydata/jingsong-cass-s4/o04
SRC=$WORK/src; HDIR=$WORK/harness; TOOLS=$WORK/tools
RUN=${1:?run}; K=${2:?K}; W1N=${3:-600000}; W2M=${4:-2000}; SETTLE=${5:-60}
OUT=$WORK/logs/$RUN/cluster-K$K; DATA=$WORK/data
mkdir -p $OUT $TOOLS
exec > >(tee -a $OUT/session.txt) 2>&1
log(){ echo "+ $(date -u +%FT%TZ) $(date +%s%3N) $*"; }
NT="$SRC/bin/nodetool -h 127.0.0.1 -p 7499"
PID=""
cleanup(){
  if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
    log "cleanup: kill $PID"; kill $PID || true
    for i in $(seq 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "cleanup: kill -9 $PID"; kill -9 $PID; } || true
  fi
  log "cleanup: CassandraDaemon processes under $WORK:"; ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -F "$WORK" || echo "  none"
}
trap cleanup EXIT
hist(){ jcmd $PID GC.class_histogram > $OUT/h-$K-$1.txt; log "histogram $1: $(grep -E ' java.net.Inet4Address( |$)' $OUT/h-$K-$1.txt | awk '{print $2, $3}') total: $(tail -1 $OUT/h-$K-$1.txt)"; }
heap(){ jcmd $PID GC.run > /dev/null; jcmd $PID GC.heap_info > $OUT/heap-$K-$1.txt; log "heap_info $1: $(grep -m1 -i 'used' $OUT/heap-$K-$1.txt)"; }

log "step 0: port check (AM2)"
if ss -ltn | egrep ':(7300|7301|7499|9342|9391)\b'; then log "ports busy, stop"; exit 1; fi
ps -eo pid,cmd | grep '[C]assandraDaemon' | grep -F "$WORK" && { log "a node of this run is already up, stop"; exit 1; } || true
log "step 1: configure K=$K, wipe data"
git -C $SRC checkout -- conf/cassandra.yaml conf/cassandra-env.sh
python3 $HDIR/configure.py $SRC $K $DATA
grep -n -A6 '^cidr_authorizer:' $SRC/conf/cassandra.yaml
grep -nE '^(authenticator|storage_port|ssl_storage_port|native_transport_port|commitlog_directory)|seeds:' $SRC/conf/cassandra.yaml
grep -n '^JMX_PORT' $SRC/conf/cassandra-env.sh
rm -rf $DATA; mkdir -p $DATA/{data,commitlog,saved_caches,hints,cdc}
log "step 2: start node"
export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M CASSANDRA_LOG_DIR=$OUT/node-logs
mkdir -p $CASSANDRA_LOG_DIR
( cd $SRC && bin/cassandra -p $WORK/cassandra.pid > $OUT/start-$K.log 2>&1 )
for i in $(seq 30); do [ -s $WORK/cassandra.pid ] && break; sleep 1; done
PID=$(cat $WORK/cassandra.pid); log "pid $PID"
unset MAX_HEAP_SIZE HEAP_NEWSIZE
ok=0
for i in $(seq 180); do
  kill -0 $PID 2>/dev/null || { log "daemon died during start"; tail -50 $CASSANDRA_LOG_DIR/system.log; exit 1; }
  if $NT status 2>/dev/null | grep -q '^UN' && [ "$($NT statusbinary 2>/dev/null | tr -d '[:space:]')" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "node not UN/running in time"; exit 1; }
$NT status; $NT statusbinary
log "cidr lines in system.log:"; grep -i cidr $CASSANDRA_LOG_DIR/system.log | cut -c1-250 || true
grep -E '^(ERROR|WARN)' $CASSANDRA_LOG_DIR/system.log | grep -i cidr && { log "cidr errors, stop"; exit 1; } || true
log "step 3: wait for the default role (cqlsh)"
ok=0
for i in $(seq 60); do
  if ( cd $SRC && timeout 60 bin/cqlsh 127.0.0.1 9342 -u cassandra -p cassandra -e "select release_version from system.local" ) > $OUT/cqlsh.txt 2>&1; then ok=1; break; fi
  sleep 2
done
cat $OUT/cqlsh.txt; [ $ok = 1 ] || { log "cqlsh never succeeded"; exit 1; }
log "step 4: group lo"
$NT updatecidrgroup lo 127.0.0.0/8
$NT reloadcidrgroupscache
G=$($NT getcidrgroupsofip 127.1.0.1); echo "getcidrgroupsofip 127.1.0.1 -> $G"
echo "$G" | grep -qw lo || { log "127.1.0.1 not in group lo, stop"; exit 1; }
$NT reloadcidrgroupscache
log "step 5: baselines"
hist base1; sleep $SETTLE; hist base2; heap base
$NT info | grep -i heap | tee $OUT/info-$K-base.txt
log "step 6: W1 JmxProbe 65536 $W1N"
( cd $TOOLS && java -cp . JmxProbe 65536 $W1N 7499 ) 2>&1 | tee $OUT/w1.txt
grep -q '^done' $OUT/w1.txt || { log "W1 failed"; exit 1; }
log "step 7: after W1"
hist w1; heap w1; $NT info | grep -i heap | tee $OUT/info-$K-w1.txt
sleep $SETTLE; hist w1b
log "step 8: flush control"
$NT reloadcidrgroupscache; hist flushed
log "step 9: W2 NativeProbe $W2M"
( cd $TOOLS && java -cp . NativeProbe $W2M 9342 ) 2>&1 | tee $OUT/w2.txt
grep -q '^done' $OUT/w2.txt || { log "W2 failed"; exit 1; }
hist w2
$NT cidrfilteringstats > $OUT/cidrfilteringstats.txt 2>&1 || true
log "node health"; grep -cE '^ERROR' $CASSANDRA_LOG_DIR/system.log || true; grep -c OutOfMemoryError $CASSANDRA_LOG_DIR/system.log || true
log "step 10: stop node"
kill $PID
for i in $(seq 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
kill -0 $PID 2>/dev/null && { log "kill -9 after 60 s"; kill -9 $PID; } || true
PID=""
rm -f $WORK/cassandra.pid
log "cluster K=$K done"
