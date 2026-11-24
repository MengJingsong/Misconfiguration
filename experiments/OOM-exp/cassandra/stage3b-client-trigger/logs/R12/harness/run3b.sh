#!/usr/bin/env bash
# R12 3-b confirm run driver (from run.sh). Usage:
#   run3b.sh <run-id> <heap e.g. 2G> <ident|distinct> <fixed:N | single:1,2,3> <hold-s>
# Auth on (tree conf), attack client logs in as role `attacker`, victim client (role `victim`, 4 connections from
# 127.2.0.1-4, 20 req/s on vks.t, CL ONE) runs from CQL-up: 60 s before the attack, during it, 60 s after the endpoint;
# if the daemon died, it is restarted on the same data (operator restart) and the victim runs 60 s more after CQL is up.
# Markers (epoch ms) in $R/markers.txt. Statement partition: $K or $W/k_sel. Tracing off (verified test arm TB).
set -u
W=/mydata/s4/3b-R12; H=$W/harness; T=$W/cassandra-base
RID=$1; HEAP=$2; VAL=$3; MODE=$4; HOLD=$5; TR=off; MON=mon50
K=${K:-$(cat $W/k_sel 2>/dev/null)}
R=$W/runs/$RID
mkdir -p $R; exec > $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T) $*"; }
mark(){ echo "$1 $(date +%s%3N)" >> $R/markers.txt; log "MARK $1"; }
. $W/creds.env
log "run $RID heap=$HEAP tracing=$TR values=$VAL monitor=$MON mode=$MODE hold=$HOLD k=$K auth=on"
[ -n "$K" ] || [ "${MODE%%:*}" = single ] || { log "ABORT: no k"; exit 1; }
if ps -eo cmd | grep -q '[C]assandraDaemon'; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
need=$(( ${HEAP%G} + 6 )); free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
rm -rf $T/data $T/logs
tar -C $T -xf $W/seed/data.tar || { log "ABORT: seed restore"; exit 1; }
EXTRA=""
[ "${HEAP%G}" -ge 8 ] && EXTRA="$EXTRA -XX:-HeapDumpOnOutOfMemoryError"
log "JVM_EXTRA_OPTS='$EXTRA'"
start_daemon(){  # $1 = unit suffix, $2 = stdout file, $3 = dump dir
  ( ulimit -n 100000; cd $T; MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$3 JVM_EXTRA_OPTS="$EXTRA" exec systemd-run --user --scope -p MemorySwapMax=0 \
      --unit=3b-r12-$RID$1 -- bin/cassandra -f > $2 2>&1 < /dev/null ) &
  PID=
  for i in $(seq 1 150); do
    sleep 2
    [ -z "$PID" ] && PID=$(pgrep -f "CassandraDaemon" | head -1)
    grep -q "Starting listening for CQL clients" $2 2>/dev/null && break
    if [ -n "$PID" ] && ! kill -0 $PID 2>/dev/null; then log "INVALID: daemon died during start"; return 1; fi
  done
  grep -q "Starting listening for CQL clients" $2 || { log "INVALID: no CQL in 300 s"; [ -n "$PID" ] && kill -9 $PID; return 1; }
  return 0
}
stop_daemon(){
  kill $PID 2>/dev/null
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
}
mark daemon_start
start_daemon "" $R/stdout.txt $R || exit 1
mark cql_up
log "daemon pid $PID up"
echo $PID > $R/pid
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
grep -i "open files" /proc/$PID/limits >> $R/vm-flags.txt
grep -oE "(authenticator|authorizer|role_manager|network_authorizer|cidr_authorizer)=[^;]*" $R/stdout.txt | head -8 > $R/auth-config.txt
setsid nohup bash $H/monitor.sh $PID $R $T < /dev/null > $R/monitor.err 2>&1 &
MPID=$!
echo $MPID > $R/monitor.pid
VPID=
if [ "${VICTIM:-1}" = 1 ] && [ "${MODE%%:*}" != single ]; then
  R12_USER=victim R12_PASS=$VPW setsid nohup python3 -I $H/client.py --victim --conns 4 --rate 20 --timeout 12 --out $R --stopfile $R/VICTIM_STOP < /dev/null > $R/victim.err 2>&1 &
  VPID=$!; echo $VPID > $R/victim.pid
  mark victim_start
  sleep 60
fi
DARG=""; [ "$VAL" = distinct ] && DARG="--distinct"
mark attack_start
if [ "${MODE%%:*}" = single ]; then
  ( for kk in $(echo ${MODE#single:} | tr , ' '); do R12_USER=attacker R12_PASS=$APW python3 -I $H/client.py --single $kk --count 20; done > $R/single.txt 2>&1 ) &
  log "calibration single ${MODE#single:} as attacker"
else
  log "client start (role attacker) --k $K --tracing $TR $DARG --fixed ${MODE#fixed:} --hold-s $HOLD"
  R12_USER=attacker R12_PASS=$APW python3 -I $H/client.py --k $K --tracing $TR $DARG --fixed ${MODE#fixed:} --hold-s $HOLD --out $R > $R/client.err 2>&1 &
fi
CPID=$!
while kill -0 $CPID 2>/dev/null && kill -0 $PID 2>/dev/null && [ ! -e $R/DISKGUARD ]; do sleep 1; done
if [ -e $R/DISKGUARD ]; then
  mark endpoint_diskguard; END=diskguard; kill -9 $PID 2>/dev/null; sleep 2; kill $CPID 2>/dev/null
elif kill -0 $PID 2>/dev/null; then
  mark endpoint_hold; END=hold
  log "client ended; daemon alive (hold end)"
else
  mark endpoint_daemon_gone; END=daemon-exit
  log "daemon gone while client running"
  sleep 3; kill $CPID 2>/dev/null
fi
wait $CPID 2>/dev/null
if [ -n "$VPID" ]; then sleep 60; mark after_window_end; fi
if [ "$END" = hold ]; then stop_daemon; fi
sleep 3
for i in $(seq 1 30); do systemctl --user is-active 3b-r12-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
kill $MPID 2>/dev/null; pkill -P $MPID 2>/dev/null
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
grep -h "Scheduling monitoring task" $R/system.log* > $R/montask.txt 2>/dev/null
if [ -s $R/montask.txt ] && ! grep -q "max operations 50\$" $R/montask.txt; then log "INVALID: monitor setting differs: $(cat $R/montask.txt)"; fi
[ -s $R/montask.txt ] || log "NOTE: no 'Scheduling monitoring task' line (no slow/failed op reached the monitor)"
ls -l $T/logs/ > $R/logs-ls.txt 2>&1
bash $H/drains.sh $T/logs > $R/drains.txt 2>&1
rm -f $T/logs/debug.log*
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
# operator restart on the same data (victim's recovery), only if the daemon died
if [ -n "$VPID" ] && [ "${END%% *}" != hold ]; then
  mkdir -p $R/restart
  mark restart_start
  if start_daemon "-restart" $R/restart/stdout.txt $R/restart; then
    mark restart_cql_up; log "restart pid $PID up"
    sleep 60; mark restart_window_end
    stop_daemon
    cp $T/logs/system.log $R/restart/ 2>/dev/null
  fi
fi
[ -n "$VPID" ] && { touch $R/VICTIM_STOP; for i in $(seq 1 30); do kill -0 $VPID 2>/dev/null || break; sleep 1; done; kill $VPID 2>/dev/null; mark victim_stop; }
for i in $(seq 1 30); do systemctl --user is-active 3b-r12-$RID-restart.scope >/dev/null 2>&1 || break; sleep 1; done
log "done"
