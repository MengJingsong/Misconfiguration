#!/usr/bin/env bash
# R20 run driver (from R15's run.sh, 2026-11-21; R15's from U6's).
# Usage: run.sh <run-id> <base|iv> <heap e.g. 2G> <H|C|S0|S0iv> <N> <k1> <trig-spec> <hold> [len|-] [trig-max-s] [k2] [trig2-spec]
#   trig-spec: none | gc (detector on this run's gc.log) | fixed:<s> | fixedfrom:<run-id> (that run's t_trig offset)
#   hold: <s after t_trig1 (t_trig2 when k1 = 0)> | holdfrom:<T-run> = max(300, 2 x (t_OOM - t_trig of it) + 60), 600 if it did not OOM
#   trig2-spec (R20 wave 2, pre-sent frames): - | sat:<free MiB> | gc | fixed:<s>
# Layout: $W/cassandra (base copy, shipped conf), $W/cassandra-iv, $W/harness, $W/runs/<run-id>.
set -u
W=/mydata/s4/r20; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; ARM=$4; N=$5; K=$6; TSPEC=$7; HOLD=$8; LEN=${9:-}; TMAX=${10:-300}; K2=${11:-0}; T2SPEC=${12:--}
[ "$LEN" = "-" ] && LEN=""
case $HEAP in *M) HMIB=${HEAP%M};; *G) HMIB=$(( ${HEAP%G} * 1024 ));; esac; HG=$(( HMIB / 1024 ))
T=$W/cassandra; [ "$BUILD" = iv ] && T=$W/cassandra-iv
R=$W/runs/$RID; STOP=$R/STOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T.%3N%z) $*"; }
log "run $RID build=$BUILD heap=$HEAP arm=$ARM N=$N k=$K trig=$TSPEC hold_after=$HOLD len=${LEN:-default} tmax=$TMAX k2=$K2 trig2=$T2SPEC diag=${R20_DIAG:-}"
case $HOLD in holdfrom:*) src=${HOLD#holdfrom:}; HOLD=$(python3 -I $H/holdfrom.py $W/runs/$src) || { log "ABORT: holdfrom $src"; exit 1; }; log "hold from $src: $HOLD s";; esac
if pgrep -f "^[^ ]*java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon" >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( HG * 13 / 10 + 4 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $T/conf/jvm11-server.options $T/conf/cassandra-env.sh $T/conf/jvm-server.options $T/build/apache-cassandra-5.0.9-SNAPSHOT.jar > $R/conf-md5.txt
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; exec env MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=r20-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do
  sleep 2
  [ -z "$PID" ] && PID=$(pgrep -f "^[^ ]*java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon" | head -1)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; exit 1; fi
done
grep -q "Starting listening for CQL clients" $R/stdout.txt || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; exit 1; }
[ "$(readlink /proc/$PID/cwd)" = "$T" ] || log "WARN: daemon cwd $(readlink /proc/$PID/cwd) != $T"
log "daemon pid $PID up"
echo $PID > $R/pid
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
grep -i "open files" /proc/$PID/limits >> $R/vm-flags.txt
grep -o -E "MaxDirectMemorySize=[0-9A-Za-z]+" $R/vm-cmdline.txt | sort -u >> $R/resolved.txt
java -cp $H Jmx 7199 get org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytes \
  org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytesPerIp >> $R/resolved.txt 2>&1
grep -o -E "native_transport_max_frame_size=[^;]*;|native_transport_max_message_size=[^;]*;|native_transport_max_threads=[^;]*;|max_mutation_size=[^;]*;" $T/logs/system.log | sort -u >> $R/resolved.txt
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 20
LA=""; [ -n "$LEN" ] && LA="--len $LEN"
case $ARM in
S0|S0iv)
  jmap -histo:live $PID > $R/histo-idle.txt 2>&1
  PL="H C"; [ "$ARM" = S0iv ] && PL="H"
  for p in $PL; do
    log "S0 payload $p"
    python3 -I $H/client.py --payload $p --n 1 --count 2 --hold-s $HOLD --out $R --tag $p $LA > $R/client-$p.err 2>&1 &
    C=$!
    sleep 1.5; jcmd $PID Thread.print > $R/threads-during-$p.txt 2>&1
    wait $C
  done
  jmap -histo:live $PID > $R/histo-after.txt 2>&1
  CP=""
  ;;
*)
  case $TSPEC in
    none) TA="--trig-at none";;
    gc) TA="--trig-at gc:$T/logs/gc.log:$HMIB --trig-max $TMAX";;
    fixed:*) TA="--trig-at $TSPEC";;
    fixedfrom:*) src=${TSPEC#fixedfrom:}
       off=$(python3 -I -c "import re,sys;s=open('$W/runs/$src/trigger.txt').read();m=re.search(r'^t_trig\S* \d+ \(\+([\d.]+) s',s,re.M);print(m.group(1) if m else '')")
       [ -z "$off" ] && { log "ABORT: no t_trig in $src/trigger.txt"; kill $PID; sleep 10; kill -9 $PID 2>/dev/null; touch $STOP; exit 1; }
       log "trigger offset from $src: +$off s"; TA="--trig-at fixed:$off";;
  esac
  MR=""; [ "$BUILD" = iv ] && MR="--min-resp 1"
  T2A=""
  if [ "$K2" -gt 0 ]; then
    case $T2SPEC in
      sat:*) T2A="--trig2-n $K2 --trig2-at sat:$T/logs/gc.log:$HMIB:${T2SPEC#sat:}";;
      gc) T2A="--trig2-n $K2 --trig2-at gc:$T/logs/gc.log:$HMIB";;
      fixed:*) T2A="--trig2-n $K2 --trig2-at $T2SPEC";;
      *) log "ABORT: bad trig2 spec $T2SPEC"; kill $PID; sleep 10; kill -9 $PID 2>/dev/null; touch $STOP; exit 1;;
    esac
    TA="$TA --trig-max $TMAX"
  fi
  log "baseline done; client start N=$N k=$K $TA $T2A"
  python3 -I $H/client.py --payload $ARM --n $N --trig-n $K $TA $T2A --hold-s $HOLD $MR --out $R --tag p0 $LA > $R/client-p0.err 2>&1 &
  CP=$!
  ;;
esac
alive(){ for c in $CP; do kill -0 $c 2>/dev/null && return 0; done; return 1; }
DISK=""; OOMSEEN=""
while alive && kill -0 $PID 2>/dev/null; do
  sleep 1
  if [ -z "$OOMSEEN" ] && grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt; then OOMSEEN=1; log "OOM line seen in stdout"; fi
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 51200 ]; then DISK="disk-guard(${f}M)"; log "DISK GUARD: stopping client"; for c in $CP; do kill $c; done; fi
done
if kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end) $DISK"
  END="hold $DISK"
else
  log "daemon gone while client running"
  END=daemon-exit
  sleep 3; for c in $CP; do kill $c 2>/dev/null; done
fi
[ -z "$OOMSEEN" ] && grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && log "OOM line seen in stdout (after loop)"
# wait for an in-progress heap dump before stopping
DW=240; [ "$HG" -ge 16 ] && DW=600
if grep -q "Dumping heap to" $R/stdout.txt && ! grep -q "Heap dump file created" $R/stdout.txt; then
  for i in $(seq 1 $DW); do grep -q "Heap dump file created" $R/stdout.txt && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
fi
if kill -0 $PID 2>/dev/null; then
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
fi
log "daemon stopped"
for c in $CP; do wait $c 2>/dev/null; done
touch $STOP
sleep 3
for i in $(seq 1 30); do systemctl --user is-active r20-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
python3 -I $H/trigsum.py $R >> $R/summary.txt 2>&1
log "done"
