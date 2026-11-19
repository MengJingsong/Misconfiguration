#!/usr/bin/env bash
# U6 run driver. Usage: run.sh <run-id> <base|iv> <heap e.g. 2G> <H|C|M|CM|S0|S0iv> <N> <hold-s> [len]
# Layout: $W/cassandra (copied tree, shipped conf), $W/cassandra-iv (patched build, shipped conf), $W/harness, $W/runs/<run-id>.
set -u
W=/mydata/s4/u6-w4; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; ARM=$4; N=$5; HOLD=$6; LEN=${7:-}
T=$W/cassandra; [ "$BUILD" = iv ] && T=$W/cassandra-iv
R=$W/runs/$RID; STOP=$R/STOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T.%3N%z) $*"; }
log "run $RID build=$BUILD heap=$HEAP arm=$ARM N=$N hold=$HOLD len=${LEN:-default}"
if pgrep -f CassandraDaemon >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( ${HEAP%G} * 13 / 10 + 4 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $T/conf/jvm11-server.options $T/conf/cassandra-env.sh $T/conf/jvm-server.options $T/build/apache-cassandra-5.0.9-SNAPSHOT.jar > $R/conf-md5.txt
rm -rf $T/data $T/logs
EXTRA=""; [ "${HEAP%G}" -ge 16 ] && EXTRA="JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError"
( ulimit -n 100000; cd $T; exec env $EXTRA MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=u6-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do
  sleep 2
  [ -z "$PID" ] && PID=$(pgrep -f "CassandraDaemon" | head -1)
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
java -cp $H Jmx 7199 get org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytes \
  org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytesPerIp > $R/resolved.txt 2>&1
grep -o -E "native_transport_max_frame_size=[^;]*;|native_transport_max_message_size=[^;]*;|native_transport_max_threads=[^;]*;|max_mutation_size=[^;]*;" $T/logs/system.log | sort -u >> $R/resolved.txt
case $ARM in M|CM|S0) python3 -I $H/client.py --ddl >> $R/driver.txt 2>&1 || log "ddl failed";; esac
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 20
LA=""; [ -n "$LEN" ] && LA="--len $LEN"
if [ "$ARM" = S0 ] || [ "$ARM" = S0iv ]; then
  jmap -histo:live $PID > $R/histo-idle.txt 2>&1
  PL="H C M"; [ "$ARM" = S0iv ] && PL="H"
  for p in $PL; do
    log "S0 payload $p"
    python3 -I $H/client.py --payload $p --n 1 --count 2 --hold-s $HOLD --out $R --tag $p $LA > $R/client-$p.err 2>&1 &
    C=$!
    sleep 1.5; jcmd $PID Thread.print > $R/threads-during-$p.txt 2>&1
    wait $C
  done
  jmap -histo:live $PID > $R/histo-after.txt 2>&1
  CP=""
else
  log "baseline done; client start N=$N"
  python3 -I $H/client.py --payload $ARM --n $N --hold-s $HOLD --out $R --tag p0 $LA > $R/client-p0.err 2>&1 &
  CP=$!
fi
alive(){ for c in $CP; do kill -0 $c 2>/dev/null && return 0; done; return 1; }
DISK=""
while alive && kill -0 $PID 2>/dev/null; do
  sleep 1
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 5120 ]; then DISK="disk-guard(${f}M)"; log "DISK GUARD: stopping client"; for c in $CP; do kill $c; done; fi
done
if kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end) $DISK"
  END="hold $DISK"
else
  log "daemon gone while client running"
  END=daemon-exit
  sleep 3; for c in $CP; do kill $c 2>/dev/null; done
fi
# wait for an in-progress heap dump before stopping
if grep -q "Dumping heap to" $R/stdout.txt && ! grep -q "Heap dump file created" $R/stdout.txt; then
  for i in $(seq 1 240); do grep -q "Heap dump file created" $R/stdout.txt && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
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
for i in $(seq 1 30); do systemctl --user is-active u6-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
