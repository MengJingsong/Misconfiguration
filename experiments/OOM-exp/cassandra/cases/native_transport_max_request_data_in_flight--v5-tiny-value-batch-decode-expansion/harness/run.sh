#!/usr/bin/env bash
# R13 run driver (from B14's run.sh). Usage: run.sh <run-id> <base|i> <heap e.g. 2G> <P|Cp> <N> <hold-s> [last-delay] [nodump]
# Layout: $W/cassandra (copied tree, shipped conf), $W/conf-i (intervention conf), $W/harness, $W/runs/<run-id>.
# Changes vs B14 (case file 2.5 item 3): daemon found only among java processes; dump wait (<= 600 s) before SIGTERM at the
# hold end; JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError for "nodump" (16 GiB runs); disk preflight heap+8 GiB (10 GiB if
# nodump); resolved in-flight values from JMX StorageService.
set -u
W=/mydata/s4/r13-w1; H=$W/harness; T=$W/cassandra
RID=$1; CONF=$2; HEAP=$3; ARM=$4; N=$5; HOLD=$6; LD=${7:-0}; ND=${8:-}
R=$W/runs/$RID; STOP=$R/STOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T%z) $*"; }
dpid(){ ps -eo pid=,comm=,args= | awk '$2=="java" && /CassandraDaemon/ {print $1}' | head -1; }
log "run $RID conf=$CONF heap=$HEAP arm=$ARM N=$N hold=$HOLD last_delay=$LD nodump=${ND:-no}"
[ -n "$(dpid)" ] && { log "ABORT: a CassandraDaemon runs"; exit 1; }
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( ${HEAP%G} + 8 )); [ "$ND" = nodump ] && need=10
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $T/conf/jvm11-server.options $T/conf/cassandra-env.sh $W/conf-i/cassandra.yaml > $R/conf-md5.txt
rm -rf $T/data $T/logs
CC=""; [ "$CONF" = i ] && CC="CASSANDRA_CONF=$W/conf-i"
XO=""; [ "$ND" = nodump ] && XO="JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError"
( ulimit -n 100000; cd $T; exec env $CC $XO MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=r13-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do
  sleep 2
  [ -z "$PID" ] && PID=$(dpid)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; exit 1; fi
done
[ -z "$PID" ] && PID=$(dpid)
grep -q "Starting listening for CQL clients" $R/stdout.txt || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; exit 1; }
log "daemon pid $PID up"
echo $PID > $R/pid
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
grep -i "open files" /proc/$PID/limits >> $R/vm-flags.txt
grep -o -E "native_transport_max_request_data_in_flight[a-z_]*=[^;]*;|native_transport_max_message_size=[^;]*;|batch_size_fail_threshold=[^;]*;|memtable_heap_space=[^;]*;|max_mutation_size=[^;]*;|native_transport_receive_queue_capacity=[^;]*;|memtable_allocation_type=[^;]*;" $T/logs/system.log | sort -u > $R/resolved.txt
java -cp $H Jmx 7199 get org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytes \
  org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytesPerIp >> $R/resolved.txt 2>&1
python3 -I $H/client.py --ddl >> $R/driver.txt 2>&1 || { log "INVALID: ddl failed"; kill $PID; }
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 20
log "baseline done; client start N=$N"
P=$(( (N + 7) / 8 )); CP=""
for p in $(seq 0 $((P - 1))); do
  s=$(( p * 8 )); n=$(( N - s < 8 ? N - s : 8 ))
  python3 -I $H/client.py --arm $ARM --conn-start $s --conn-n $n --hold-s $HOLD --last-delay $LD --out $R --tag p$p > $R/client-p$p.err 2>&1 &
  CP="$CP $!"
done
alive(){ for c in $CP; do kill -0 $c 2>/dev/null && return 0; done; return 1; }
DISK=""
while alive && kill -0 $PID 2>/dev/null; do
  sleep 1
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 6144 ] && [ -z "$DISK" ]; then DISK="disk-guard(${f}M)"; log "DISK GUARD: stopping client"; for c in $CP; do kill $c; done; fi
done
if kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end) $DISK"
  if grep -q "Dumping heap to" $R/stdout.txt && ! grep -q "Heap dump file created" $R/stdout.txt; then
    log "dump in progress at hold end: waiting (<= 600 s)"
    for i in $(seq 1 600); do grep -q "Heap dump file created" $R/stdout.txt && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
    log "dump wait ended after ${i} s"
    for i in $(seq 1 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  fi
  if kill -0 $PID 2>/dev/null; then
    kill $PID
    for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
  fi
  END="hold $DISK"
else
  log "daemon gone while client running"
  END=daemon-exit
  sleep 3; for c in $CP; do kill $c 2>/dev/null; done
fi
for c in $CP; do wait $c 2>/dev/null; done
touch $STOP
sleep 3
for i in $(seq 1 30); do systemctl --user is-active r13-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
