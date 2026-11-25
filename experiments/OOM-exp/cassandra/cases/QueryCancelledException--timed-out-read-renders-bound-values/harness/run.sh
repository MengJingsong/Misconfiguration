#!/usr/bin/env bash
# U16 run driver (from R12's). Usage:
#   run.sh <run-id> <base|iv> <heap: 2G|4G|8G|15872M|31744M|auto> <K> <fixed:N | ramp:32,48,64,96 | single:1,2,3,4 | idle> <hold-s>
# Layout: $W/cassandra-<base|iv>, $W/harness, $W/seed/data.tar, $W/runs/<run-id>, $W/dumps.
set -u
W=/mydata/s4/u16; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; K=$4; MODE=$5; HOLD=$6
T=$W/cassandra-$BUILD; R=$W/runs/$RID
mkdir -p $R $W/dumps; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T.%3N) $*"; }
log "run $RID build=$BUILD heap=$HEAP k=$K mode=$MODE hold=$HOLD"
# preflight
if ps -eo cmd | grep -q '[C]assandraDaemon'; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
case "$HEAP" in *G) hg=${HEAP%G};; *M) hg=$(( ${HEAP%M} / 1024 ));; auto) hg=32;; esac
need=$(( hg + 60 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
rm -rf $T/data $T/logs
tar -C $T -xf $W/seed/data.tar || { log "ABORT: seed restore"; exit 1; }
EXTRA=""
[ "$hg" -ge 15 ] && EXTRA="-XX:-HeapDumpOnOutOfMemoryError"
log "JVM_EXTRA_OPTS='$EXTRA'"
if [ "$HEAP" = auto ]; then
  ( ulimit -n 100000; cd $T; unset MAX_HEAP_SIZE HEAP_NEWSIZE; CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EXTRA" exec systemd-run --user --scope -p MemorySwapMax=0 \
      --unit=u16-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
else
  ( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EXTRA" exec systemd-run --user --scope -p MemorySwapMax=0 \
      --unit=u16-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
fi
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
case "${MODE%%:*}" in
  fixed) CARGS="--fixed ${MODE#fixed:} --hold-s $HOLD";;
  ramp) CARGS="--ramp ${MODE#ramp:} --step-s $HOLD";;
esac
if [ "${MODE%%:*}" = single ]; then
  log "client single ${MODE#single:} count $HOLD"
  ( for kk in $(echo ${MODE#single:} | tr , ' '); do python3 -I $H/client.py --single $kk --count $HOLD; done > $R/single.txt 2>&1 ) &
elif [ "$MODE" = idle ]; then
  log "idle $HOLD s"
  ( sleep $HOLD ) &
else
  log "client start --k $K $CARGS"
  python3 -I $H/client.py --k $K --tracing off $CARGS --out $R > $R/client.err 2>&1 &
fi
CPID=$!
while kill -0 $CPID 2>/dev/null && kill -0 $PID 2>/dev/null && [ ! -e $R/DISKGUARD ]; do sleep 1; done
if [ -e $R/DISKGUARD ]; then
  log "disk guard fired"; END=diskguard; kill -9 $PID 2>/dev/null; sleep 2; kill $CPID 2>/dev/null
elif kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end)"
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
  END=hold
else
  log "daemon gone while client running (epoch $(date +%s.%N | cut -c1-14))"
  END=daemon-exit
  sleep 3; kill $CPID 2>/dev/null
fi
wait $CPID 2>/dev/null
sleep 3
for i in $(seq 1 60); do systemctl --user is-active u16-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
kill $MPID 2>/dev/null; pkill -P $MPID 2>/dev/null
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
grep -h "Scheduling monitoring task" $R/system.log* > $R/montask.txt 2>/dev/null
if [ -s $R/montask.txt ] && ! grep -q "max operations 50\$" $R/montask.txt; then log "INVALID: monitor setting differs: $(cat $R/montask.txt)"; fi
[ -s $R/montask.txt ] || log "NOTE: no 'Scheduling monitoring task' line"
ls -l $T/logs/ > $R/logs-ls.txt 2>&1
# debug.log* -> squashed (hex runs >= 64 -> H) -> counts and drains; then delete debug.log*
log "debug.log* bytes $(stat -c %s $T/logs/debug.log* 2>/dev/null | awk '{s+=$1} END{print s+0}'), files $(ls $T/logs | grep -c '^debug.log')"
# rolled archives (valid zips), rolled files whose compression the stop cut short (*.tmp: logback renames before it
# compresses; an incomplete zip is skipped, its .tmp source is read instead), then the live debug.log
{ for f in $(ls -tr $T/logs/ | grep -E '^debug\.log\..*\.(zip|tmp)$' | sed "s|^|$T/logs/|") $T/logs/debug.log; do
    [ -e "$f" ] || continue
    case "$f" in *.zip) unzip -tqq "$f" >/dev/null 2>&1 && unzip -p "$f" ;; *) cat "$f" ;; esac
  done; } | timeout 1200 python3 -I $H/squash.py > $W/tmp-squashed-$RID.txt
echo "logged_qc_events $(grep -acF 'StorageProxy.java:2223 - Query cancelled (timeout)' $W/tmp-squashed-$RID.txt)" > $R/debugcounts.txt
echo "logged_qc_messages $(grep -aoF 'QueryCancelledException: Query cancelled for taking too long' $W/tmp-squashed-$RID.txt | wc -l)" >> $R/debugcounts.txt
echo "squashed_bytes $(stat -c %s $W/tmp-squashed-$RID.txt)" >> $R/debugcounts.txt
grep -a 'StorageProxy.java:2223 - Query cancelled (timeout)' $W/tmp-squashed-$RID.txt | cut -c1-110 > $R/qc-events.txt
bash $H/drains.sh $W/tmp-squashed-$RID.txt > $R/drains.txt 2>&1
grep -a -m3 -A12 'StorageProxy.java:2223 - Query cancelled (timeout)' $W/tmp-squashed-$RID.txt | cut -c1-300 > $R/qc-excerpt.txt
rm -f $W/tmp-squashed-$RID.txt $T/logs/debug.log*
for d in $R/*.hprof; do [ -e "$d" ] && mv "$d" $W/dumps/$RID.hprof; done
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
