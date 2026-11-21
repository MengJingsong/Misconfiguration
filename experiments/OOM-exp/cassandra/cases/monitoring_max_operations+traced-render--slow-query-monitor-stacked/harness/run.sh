#!/usr/bin/env bash
# R12 run driver (from B11's). Usage:
#   run.sh <run-id> <base|iv> <heap e.g. 2G> <on|off> <ident|distinct> <mon50|mon0> <fixed:N | ramp:8,13,.. | single:1,2,3> <hold-s>
# Statement partition: $K or the content of $W/k_sel. Layout: $W/cassandra-<base|iv>, $W/harness, $W/seed/data.tar, $W/runs/<run-id>.
set -u
W=/mydata/s4/r12-w5; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; TR=$4; VAL=$5; MON=$6; MODE=$7; HOLD=$8
K=${K:-$(cat $W/k_sel 2>/dev/null)}
T=$W/cassandra-$BUILD; R=$W/runs/$RID
mkdir -p $R; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T) $*"; }
log "run $RID build=$BUILD heap=$HEAP tracing=$TR values=$VAL monitor=$MON mode=$MODE hold=$HOLD k=$K"
[ -n "$K" ] || { log "ABORT: no k"; exit 1; }
# preflight
if ps -eo cmd | grep -q '[C]assandraDaemon'; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( ${HEAP%G} + 6 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
rm -rf $T/data $T/logs
tar -C $T -xf $W/seed/data.tar || { log "ABORT: seed restore"; exit 1; }
EXTRA=""
[ "$MON" = mon0 ] && EXTRA="-Dcassandra.monitoring_max_operations=0"
[ "${HEAP%G}" -ge 8 ] && EXTRA="$EXTRA -XX:-HeapDumpOnOutOfMemoryError"
log "JVM_EXTRA_OPTS='$EXTRA'"
( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EXTRA" exec systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=r12-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do
  sleep 2
  [ -z "$PID" ] && PID=$(pgrep -f "CassandraDaemon" | head -1)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; exit 1; fi
done
grep -q "Starting listening for CQL clients" $R/stdout.txt || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; exit 1; }
log "daemon pid $PID up"
echo $PID > $R/pid
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
grep -i "open files" /proc/$PID/limits >> $R/vm-flags.txt
setsid nohup bash $H/monitor.sh $PID $R $T < /dev/null > $R/monitor.err 2>&1 &
MPID=$!
echo $MPID > $R/monitor.pid
if [ "${MODE%%:*}" = fixed ]; then CARGS="--fixed ${MODE#fixed:} --hold-s $HOLD"; else CARGS="--ramp ${MODE#ramp:} --step-s $HOLD"; fi
DARG=""; [ "$VAL" = distinct ] && DARG="--distinct"
log "client start --k $K --tracing $TR $DARG $CARGS"
if [ "${MODE%%:*}" = single ]; then
  ( for kk in $(echo ${MODE#single:} | tr , ' '); do python3 -I $H/client.py --single $kk --count 20; done > $R/single.txt 2>&1 ) &
else
  python3 -I $H/client.py --k $K --tracing $TR $DARG $CARGS --out $R > $R/client.err 2>&1 &
fi
CPID=$!
while kill -0 $CPID 2>/dev/null && kill -0 $PID 2>/dev/null && [ ! -e $R/DISKGUARD ]; do sleep 1; done
if [ -e $R/DISKGUARD ]; then
  log "disk guard fired"; END=diskguard; kill -9 $PID 2>/dev/null; sleep 2; kill $CPID 2>/dev/null
elif kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end)"
  [ "$TR" = on ] && [ "${TRACECHECK:-0}" = 1 ] && python3 -I $H/client.py --trace-check > $R/trace-check.txt 2>&1
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
  END=hold
else
  log "daemon gone while client running"
  END=daemon-exit
  sleep 3; kill $CPID 2>/dev/null
fi
wait $CPID 2>/dev/null
sleep 3
for i in $(seq 1 30); do systemctl --user is-active r12-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
kill $MPID 2>/dev/null; pkill -P $MPID 2>/dev/null
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
grep -h "Scheduling monitoring task" $R/system.log* > $R/montask.txt 2>/dev/null
case "$MON" in mon50) WANT="max operations 50";; mon0) WANT="max operations 0";; esac
if [ -s $R/montask.txt ] && ! grep -q "$WANT\$" $R/montask.txt; then log "INVALID: monitor setting differs: $(cat $R/montask.txt)"; fi
[ -s $R/montask.txt ] || log "NOTE: no 'Scheduling monitoring task' line (no slow/failed op reached the monitor)"
ls -l $T/logs/ > $R/logs-ls.txt 2>&1
bash $H/drains.sh $T/logs > $R/drains.txt 2>&1
rm -f $T/logs/debug.log*
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
