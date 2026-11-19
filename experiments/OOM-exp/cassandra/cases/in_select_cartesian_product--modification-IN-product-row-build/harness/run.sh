#!/usr/bin/env bash
# U7 run driver (case file §2.5). Usage: run.sh <run-id> <base|i|a|g> <2G|4G|8G|16G|auto> <step> [<step> ...]
# step = kind:P:Q:K0[:user]. Layout: $W/cassandra (copied tree, shipped conf), $W/conf-{i,a,g}, $W/harness, $W/runs/<run-id>.
set -u
W=/mydata/s4/u7-w4; H=$W/harness; T=$W/cassandra
RID=$1; CONF=$2; HEAP=$3; shift 3; STEPS="$*"
R=$W/runs/$RID; STOP=$R/STOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T%z) $*"; }
log "run $RID conf=$CONF heap=$HEAP steps=$STEPS"
if pgrep -f 'org.apache.cassandra.service.CassandraDaemon' >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
if [ "$HEAP" = auto ]; then need=8; else need=$(( ${HEAP%G} + 6 )); fi
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
case $CONF in base) CD=$T/conf;; i) CD=$W/conf-i;; a) CD=$W/conf-a;; g) CD=$W/conf-g;; esac
md5sum $CD/cassandra.yaml $CD/jvm11-server.options $CD/cassandra-env.sh $CD/jvm-server.options > $R/conf-md5.txt
grep -n "^authenticator\|^in_select_cartesian" $CD/cassandra.yaml >> $R/conf-md5.txt
rm -rf $T/data $T/logs
EX=""; HS=""
case $HEAP in 2G|4G) ;; *) EX="-XX:-HeapDumpOnOutOfMemoryError";; esac
[ "$HEAP" != auto ] && HS="MAX_HEAP_SIZE=$HEAP"
CAP=600; case $HEAP in 16G|auto) CAP=1500;; esac
( ulimit -n 100000; cd $T; exec env CASSANDRA_CONF=$CD $HS JVM_EXTRA_OPTS="$EX" CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=u7-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
PID=
for i in $(seq 1 150); do
  sleep 2
  [ -z "$PID" ] && PID=$(pgrep -f 'org.apache.cassandra.service.CassandraDaemon' | head -1)
  grep -q "Starting listening for CQL clients" $R/stdout.txt 2>/dev/null && break
  if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; exit 1; fi
done
grep -q "Starting listening for CQL clients" $R/stdout.txt || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; exit 1; }
log "daemon pid $PID up"
echo $PID > $R/pid
[ -n "$EX" ] && touch $R/nodump
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
grep -i "open files" /proc/$PID/limits >> $R/vm-flags.txt
grep -o -E "native_transport_max_request_data_in_flight[a-z_]*=[^;]*;|native_transport_max_message_size=[^;]*;|in_select_cartesian_product[a-z_]*=[^;]*;|memtable_heap_space=[^;]*;|max_mutation_size=[^;]*;|native_transport_receive_queue_capacity=[^;]*;|memtable_allocation_type=[^;]*;|authenticator=[^;]*;|commitlog_segment_size=[^;]*;|native_transport_max_threads=[^;]*;|write_request_timeout=[^;]*;|native_transport_timeout=[^;]*;" $T/logs/system.log | sort -u > $R/resolved.txt
AUTH=""; [ "$CONF" != base ] && AUTH=--auth
python3 -I $H/u7.py ddl $AUTH >> $R/driver.txt 2>&1 || { log "INVALID: ddl failed"; kill $PID; }
SU=""; [ "$CONF" != base ] && SU="--user cassandra"
python3 -I $H/u7.py settings $SU > $R/settings.txt 2>&1
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 20
log "baseline done"
T0=$(date +%s); END=""
# Amendment 2026-11-18: the endpoint is reached once the OOM line is in stdout and the dump (if any) is written;
# the shipped OnOutOfMemoryError kill did not fire in T-1..3/IA-1/B4, so wait 30 s for it, then stop the daemon.
oom_done(){ grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt || return 1
  [ -e $R/nodump ] || grep -q "Heap dump file created" $R/stdout.txt || return 1
  return 0; }
for st in $STEPS; do
  IFS=: read kind p q k0 user <<< "$st"
  kill -0 $PID 2>/dev/null || { log "daemon gone before step $st"; END="daemon-exit"; break; }
  UA=""; [ -n "${user:-}" ] && UA="--user $user"
  log "step $st start"
  python3 -I $H/u7.py send --kind $kind --p $p --q $q --k0 $k0 $UA --out $R/client.txt >> $R/client.err 2>&1 &
  CP=$!
  while kill -0 $CP 2>/dev/null && kill -0 $PID 2>/dev/null; do
    sleep 1
    if [ $(( $(date +%s) - T0 )) -ge $CAP ]; then log "CAP ${CAP}s reached in step $st"; END="cap"; break; fi
    f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
    [ "$f" -lt 4096 ] && { log "DISK GUARD ${f}M"; END="disk-guard"; break; }
    if oom_done; then log "OOM endpoint in step $st (client alive); 30 s for OnOutOfMemoryError"; sleep 30; END="oom"; break; fi
  done
  [ -n "$END" ] && break
  if ! kill -0 $PID 2>/dev/null; then log "daemon gone during step $st"; END="daemon-exit"; sleep 3; kill $CP 2>/dev/null; break; fi
  # Amendment 2026-11-18 (stage 2): a client that lost its connection (no server response) does not end the step:
  # the request keeps running on the NTR thread, so wait for daemon exit or the per-run cap (§2.5 "to completion or daemon exit").
  if tail -1 $R/client.txt | grep -q -E "outcome=ERR (NoHostAvailable|ConnectionShutdown|OperationTimedOut|ConnectionException)"; then
    log "step $st client lost its connection: $(tail -1 $R/client.txt | cut -c1-160); waiting for daemon exit or cap"
    while kill -0 $PID 2>/dev/null; do
      sleep 2
      if [ $(( $(date +%s) - T0 )) -ge $CAP ]; then log "CAP ${CAP}s reached in step $st (daemon alive)"; END="cap"; break; fi
      if oom_done; then log "OOM endpoint in step $st; 30 s for OnOutOfMemoryError"; sleep 30; END="oom"; break; fi
    done
    [ -z "$END" ] && { log "daemon gone during step $st (after client loss)"; END="daemon-exit"; }
    break
  fi
  wait $CP
  log "step $st client done: $(tail -1 $R/client.txt)"
  sleep 15
  python3 -I $H/u7.py count --k $k0 $UA >> $R/client.txt 2>&1
  python3 -I $H/u7.py count --k $(( k0 + p - 1 )) $UA >> $R/client.txt 2>&1
done
[ -z "$END" ] && END="survived"
if kill -0 $PID 2>/dev/null; then
  log "stopping daemon ($END)"
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
fi
pkill -f "$H/u7.py" 2>/dev/null
touch $STOP
sleep 3
for i in $(seq 1 30); do systemctl --user is-active u7-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="OOM($END) oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/debug.log $T/logs/gc.log* $R/ 2>/dev/null
gzip -f $R/debug.log 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
log "done"
