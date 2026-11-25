#!/usr/bin/env bash
# B28 run driver (stage 2, 2026-11-24; structure from R15's run.sh).
# Usage: run.sh <run-id> <base|iv|basewait> <heap e.g. 2G> <traced|untraced> <spec> <hold-s>
#   spec: N (fixed, all N together) | ramp:1,2,4,8 (60 s per step; hold-s = step length) | s0 (shakedown)
#   basewait = base build with JVM_EXTRA_OPTS=-Dcassandra.wait_for_tracing_events_timeout_secs=10 (optional I2b only)
# Layout: $W/cassandra (base copy, shipped conf), $W/cassandra-iv, $W/harness, $W/runs/<run-id>.
set -u
W=/mydata/s4/b28; H=$W/harness
RID=$1; BUILD=$2; HEAP=$3; TR=$4; SPEC=$5; HOLD=$6
case $HEAP in *M) HMIB=${HEAP%M};; *G) HMIB=$(( ${HEAP%G} * 1024 ));; esac; HG=$(( HMIB / 1024 ))
T=$W/cassandra; [ "$BUILD" = iv ] && T=$W/cassandra-iv
EXTRA=""; [ "$BUILD" = basewait ] && EXTRA="-Dcassandra.wait_for_tracing_events_timeout_secs=10"
FL=2; [ "$TR" = untraced ] && FL=0
R=$W/runs/$RID; STOP=$R/STOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T.%3N%z) $*"; }
log "run $RID build=$BUILD heap=$HEAP tracing=$TR flags=$FL spec=$SPEC hold=$HOLD extra='$EXTRA'"
if pgrep -f "^[^ ]*java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon" >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge 60 ] || { log "ABORT: /mydata free ${free}G < 60G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $T/conf/jvm11-server.options $T/conf/cassandra-env.sh $T/conf/jvm-server.options $T/build/apache-cassandra-5.0.9-SNAPSHOT.jar > $R/conf-md5.txt
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; exec env MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$EXTRA" setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=b28-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
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
grep -o -E "MaxDirectMemorySize=[0-9A-Za-z]+|MaxHeapSize=[0-9]+|wait_for_tracing_events_timeout_secs=[0-9]+" $R/vm-flags.txt $R/vm-cmdline.txt | sort -u >> $R/resolved.txt
java -cp $H Jmx 7199 get org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytes \
  org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytesPerIp >> $R/resolved.txt 2>&1
grep -o -E "native_transport_max_frame_size=[^;]*;|native_transport_max_threads=[^;]*;|max_mutation_size=[^;]*;|memtable_heap_space=[^;]*;|[^_]write_request_timeout=[^;]*;|commitlog_segment_size=[^;]*;|native_transport_rate_limiting_enabled=[^;]*;|native_transport_max_request_data_in_flight[a-z_]*=[^;]*;" $T/logs/system.log | sort -u >> $R/resolved.txt
python3 -I $H/client.py --ddl >> $R/driver.txt 2>&1 || log "ddl failed"
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 15
TP="org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=TracingStage"
case $SPEC in
s0)
  for L in 1000000 1000000 1000000 16000000 16000000 16000000; do
    b=$(java -cp $H Jmx 7199 get "$TP,name=CompletedTasks" Value | cut -d'|' -f3); b=${b//[^0-9]/}; b=${b:-0}
    python3 -I $H/client.py --n 1 --count 1 --len $L --flags $FL --out $R --tag s0 > $R/client-s0.err 2>&1
    sleep 4
    a=$(java -cp $H Jmx 7199 get "$TP,name=CompletedTasks" Value | cut -d'|' -f3); a=${a//[^0-9]/}; a=${a:-0}
    log "S0 len=$L TracingStage CompletedTasks $b -> $a (+$(( a - b )))"
  done
  java -cp $H Jmx 7199 query "org.apache.cassandra.metrics:type=ThreadPools,scope=TracingStage,*" Value > $R/s0-jmx-names.txt 2>&1
  java -cp $H Jmx 7199 query "org.apache.cassandra.metrics:type=DroppedMessage,scope=_TRACE,*" Count >> $R/s0-jmx-names.txt 2>&1
  python3 -I $H/client.py --traces > $R/s0-traces.txt 2>&1
  log "S0 traces: $(head -c 300 $R/s0-traces.txt | tr '\n' ' ')"
  CP=""
  ;;
ramp:*)
  log "load start ramp ${SPEC#ramp:} step ${HOLD}s"
  python3 -I $H/client.py --ramp ${SPEC#ramp:} --step-s $HOLD --flags $FL --out $R --tag p0 > $R/client-p0.err 2>&1 &
  CP=$!
  ;;
*)
  log "load start N=$SPEC hold ${HOLD}s"
  python3 -I $H/client.py --n $SPEC --hold-s $HOLD --flags $FL --out $R --tag p0 > $R/client-p0.err 2>&1 &
  CP=$!
  ;;
esac
alive(){ for c in $CP; do kill -0 $c 2>/dev/null && return 0; done; return 1; }
OOMSEEN=""
while alive && kill -0 $PID 2>/dev/null; do
  sleep 1
  if [ -z "$OOMSEEN" ] && grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt; then OOMSEEN=1; log "OOM line seen in stdout"; fi
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 61440 ]; then log "DISK GUARD (${f}M): stopping client"; for c in $CP; do kill $c; done; fi
done
if kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end)"
  END="hold"
else
  log "daemon gone while client running"
  END=daemon-exit
  sleep 3; for c in $CP; do kill $c 2>/dev/null; done
fi
[ -z "$OOMSEEN" ] && grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && log "OOM line seen in stdout (after loop)"
if grep -q "Dumping heap to" $R/stdout.txt && ! grep -q "Heap dump file created" $R/stdout.txt; then
  for i in $(seq 1 600); do grep -q "Heap dump file created" $R/stdout.txt && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
fi
if kill -0 $PID 2>/dev/null; then
  jcmd $PID Thread.print > $R/threads-at-end.txt 2>&1
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
fi
log "daemon stopped"
for c in $CP; do wait $c 2>/dev/null; done
touch $STOP
sleep 3
for i in $(seq 1 30); do systemctl --user is-active b28-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
du -sm $T/data/commitlog $T/data/hints $T/data/data/system_traces > $R/du-end.txt 2>&1
sleep 4
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
