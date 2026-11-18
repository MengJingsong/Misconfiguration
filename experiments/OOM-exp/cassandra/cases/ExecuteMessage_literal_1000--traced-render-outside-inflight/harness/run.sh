#!/usr/bin/env bash
# B11 run driver. Usage: run.sh <run-id> <base|iv> <heap e.g. 2G> <on|off> <fixed:N | ramp:8,13,..> <hold-s>
# Workdir layout: $W/cassandra-<base|iv>, $W/harness, $W/runs/<run-id>.
set -u
W=/mydata/s4/b11-w1; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; TR=$4; MODE=$5; HOLD=$6
T=$W/cassandra-$BUILD; R=$W/runs/$RID
mkdir -p $R; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T) $*"; }
log "run $RID build=$BUILD heap=$HEAP tracing=$TR mode=$MODE hold=$HOLD"
# preflight
if pgrep -f CassandraDaemon >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( ${HEAP%G} + 4 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R exec systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=b11-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
# wait for CQL (<= 300 s)
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
cat /proc/$PID/limits | grep -i "open files" >> $R/vm-flags.txt
python3 -I $H/client.py --ddl >> $R/driver.txt 2>&1 || { log "INVALID: ddl failed"; kill $PID; }
sleep 3
setsid nohup $H/monitor.sh $PID $R $T < /dev/null > $R/monitor.err 2>&1 &
if [ "${MODE%%:*}" = fixed ]; then CARGS="--fixed ${MODE#fixed:} --hold-s $HOLD"; else CARGS="--ramp ${MODE#ramp:} --step-s $HOLD"; fi
log "client start $CARGS"
python3 -I $H/client.py --tracing $TR $CARGS --out $R > $R/client.err 2>&1 &
CPID=$!
while kill -0 $CPID 2>/dev/null && kill -0 $PID 2>/dev/null; do sleep 1; done
if kill -0 $PID 2>/dev/null; then
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
for i in $(seq 1 30); do systemctl --user is-active b11-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
pkill -f "monitor.sh $PID" 2>/dev/null
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
