#!/usr/bin/env bash
# B14 run driver. Usage: run.sh <run-id> <base|i> <heap e.g. 2G> <T|C|P> <N> <hold-s>
# Layout: $W/cassandra (copied tree, shipped conf), $W/conf-i (intervention conf), $W/harness, $W/runs/<run-id>.
set -u
W=/mydata/s4/b14-w3; H=$W/harness; T=$W/cassandra
RID=$1; CONF=$2; HEAP=$3; ARM=$4; N=$5; HOLD=$6
R=$W/runs/$RID; STOP=$R/STOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T%z) $*"; }
log "run $RID conf=$CONF heap=$HEAP arm=$ARM N=$N hold=$HOLD"
if pgrep -f CassandraDaemon >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( ${HEAP%G} + 8 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $T/conf/jvm11-server.options $T/conf/cassandra-env.sh $W/conf-i/cassandra.yaml > $R/conf-md5.txt
rm -rf $T/data $T/logs
CC=""; [ "$CONF" = i ] && CC="CASSANDRA_CONF=$W/conf-i"
( ulimit -n 100000; cd $T; exec env $CC MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=b14-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
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
grep -o -E "native_transport_max_request_data_in_flight[a-z_]*=[^;]*;|native_transport_max_message_size=[^;]*;|batch_size_fail_threshold=[^;]*;|memtable_heap_space=[^;]*;|max_mutation_size=[^;]*;|native_transport_receive_queue_capacity=[^;]*;|memtable_allocation_type=[^;]*;" $T/logs/system.log | sort -u > $R/resolved.txt
python3 -I $H/client.py --ddl >> $R/driver.txt 2>&1 || { log "INVALID: ddl failed"; kill $PID; }
setsid nohup $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 20
log "baseline done; client start N=$N"
P=$(( (N + 7) / 8 )); CP=""
for p in $(seq 0 $((P - 1))); do
  s=$(( p * 8 )); n=$(( N - s < 8 ? N - s : 8 ))
  python3 -I $H/client.py --arm $ARM --conn-start $s --conn-n $n --hold-s $HOLD --out $R --tag p$p > $R/client-p$p.err 2>&1 &
  CP="$CP $!"
done
alive(){ for c in $CP; do kill -0 $c 2>/dev/null && return 0; done; return 1; }
DISK=""
while alive && kill -0 $PID 2>/dev/null; do
  sleep 1
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 6144 ]; then DISK="disk-guard(${f}M)"; log "DISK GUARD: stopping client"; for c in $CP; do kill $c; done; fi
done
if kill -0 $PID 2>/dev/null; then
  log "client ended; daemon alive (hold end) $DISK"
  [ "$ARM" = T ] && [ "$N" = 1 ] && { k=$(awk '$4=="VOID"{print $5}' $R/completions-p0.txt | tail -1 | cut -d= -f2); [ -n "$k" ] && python3 -I $H/client.py --check $k >> $R/driver.txt 2>&1; }
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
  END="hold $DISK"
else
  log "daemon gone while client running"
  END=daemon-exit
  sleep 3; for c in $CP; do kill $c 2>/dev/null; done
fi
for c in $CP; do wait $c 2>/dev/null; done
touch $STOP
sleep 3
for i in $(seq 1 30); do systemctl --user is-active b14-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
