#!/usr/bin/env bash
# C8 stage 3-b confirm (2026-11-24): restart lifetime after an attack OOM (claim "after restart an unfinished SAI index is
# built again"). Usage: restart-life.sh <run-id> [cap-s]
# The node is started on the data the attack lifetime left (no wipe, the operator's plain restart, commit-log replay
# included), same budget and auth. No attacker request at all. The victim role runs from CQL-up. Endpoint: daemon gone,
# initial build complete ("became queryable"), disk guard (< 4 GiB free) or cap. Then node stopped.
set -u
. $(dirname "$0")/common.sh
RID=$1; CAP=${2:-900}; R=$W/runs/$RID; VSTOP=$R/VSTOP; mkdir -p $R; exec >> $R/driver.txt 2>&1
log "RESTART lifetime $RID (data left by the previous attack lifetime) heap=$HEAP direct=$DIRECT cap=${CAP}s"
[ -n "$(dpid)" ] && { log "ABORT: a CassandraDaemon runs"; exit 1; }
du -sh $T/data/data/c8 $T/data/data/keyspace1 $T/data/commitlog > $R/data-du.txt 2>&1
ls -l $T/data/data/c8/big-*/ > $R/c8-big-dir-start.txt 2>&1
mv $T/logs $T/logs.prev 2>/dev/null; rm -rf $T/logs.prev
T0=$(date +%s)
# start_node waits <= 300 s for CQL; commit-log replay may take longer, so start here with a longer wait
( ulimit -n 100000; cd $T; exec env -u HEAP_NEWSIZE CASSANDRA_CONF=$CONF MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
    CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 --unit=3b-c8-$RID -- \
    bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=; END=""
for i in $(seq 1 $CAP); do
  sleep 1
  [ -z "$PID" ] && PID=$(dpid) && [ -n "$PID" ] && { log "daemon pid $PID"; echo $PID > $R/pid; monitors $PID $R $R/STOP; }
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then END=daemon-exit; log "daemon gone at_ms $(ems)"; break; fi
  if [ -z "${UP:-}" ] && grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null; then
    UP=1; log "CQL up at_ms $(ems) ($(( $(date +%s) - T0 )) s after start); victim start"
    setsid nohup python3 -I $H/victim.py --user victim --pw $VPW --rate 10 --out $R/victim.txt --stop $VSTOP --src 127.0.0.1 < /dev/null > $R/victim.err 2>&1 &
    VP=$!
  fi
  grep -q "Index \[v_idx\] became queryable" $T/logs/system.log 2>/dev/null && { END=build-complete; break; }
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  [ "$f" -lt 4096 ] && { END="disk-guard(${f}M)"; break; }
done
[ -z "$END" ] && END=cap
log "endpoint $END at_ms $(ems) ($(( $(date +%s) - T0 )) s after start)"
if [ "$END" = daemon-exit ]; then for i in $(seq 1 120); do grep -q "Heap dump file created" $R/stdout.txt && break; grep -q "Dumping heap" $R/stdout.txt || break; sleep 1; done; fi
sleep 10; touch $VSTOP
stop_node $RID
sleep 2; [ -n "${VP:-}" ] && kill $VP 2>/dev/null
stop_monitors $R
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/debug.log* $T/logs/gc.log* $R/ 2>/dev/null
log "done; leftovers: daemon='$(dpid)' victim='$(pgrep -f "victim.py.*$R")' sampler='$(pgrep -f "C8Sampler 7199 $R/")'"
