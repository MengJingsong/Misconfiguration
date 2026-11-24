#!/usr/bin/env bash
# U7 stage 3-b confirm run driver (2026-11-23), from the stage-2 run.sh (case file §2.5). Usage: run.sh <run-id> <2G> <step>
# step = kind:P:Q:K0 (always sent as role u7atk). Layout: $W/cassandra (copied tree), $W/conf-auth, $W/harness, $W/runs/<run-id>.
# Changes from stage 2: conf-auth only (PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager, every capacity
# at its default); ddl as superuser creates schema + roles + GRANTs; privcheck as the attacker; a victim role runs a steady
# load from 60 s before the send to the end; the OOM line's first appearance is logged; after the endpoint the daemon is
# left up 120 s (not 30 s) so the victim's "after" view is recorded, then stopped as in stage 2.
set -u
W=/mydata/s4/3b-U7; H=$W/harness; T=$W/cassandra; CD=$W/conf-auth
RID=$1; HEAP=$2; shift 2; STEPS="$*"
R=$W/runs/$RID; STOP=$R/STOP; VSTOP=$R/VSTOP
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T.%3N%z) $*"; }
log "run $RID conf=auth heap=$HEAP steps=$STEPS"
if pgrep -f 'org.apache.cassandra.service.CassandraDaemon' >/dev/null; then log "ABORT: a CassandraDaemon runs"; exit 1; fi
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
need=$(( ${HEAP%G} + 6 ))
[ "$free" -ge "$need" ] || { log "ABORT: /mydata free ${free}G < ${need}G"; exit 1; }
log "free ${free}G"
md5sum $CD/cassandra.yaml $CD/jvm11-server.options $CD/cassandra-env.sh $CD/jvm-server.options > $R/conf-md5.txt
diff $T/conf/cassandra.yaml $CD/cassandra.yaml >> $R/conf-md5.txt
grep -n "^authenticator\|^authorizer\|^role_manager\|^network_authorizer\|^in_select_cartesian" $CD/cassandra.yaml >> $R/conf-md5.txt
rm -rf $T/data $T/logs
# Deviation (3-b confirm): no `systemd-run --user --scope -p MemorySwapMax=0` (needs linger, i.e. sudo, not available to
# this session); plain setsid nohup; monitor.sh logs VmSwap of the daemon every 2 s instead (must stay 0). No memory limit either way.
( ulimit -n 100000; cd $T; exec env CASSANDRA_CONF=$CD MAX_HEAP_SIZE=$HEAP JVM_EXTRA_OPTS="" CASSANDRA_HEAPDUMP_DIR=$R setsid nohup \
    bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
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
jcmd $PID VM.flags > $R/vm-flags.txt 2>&1
jcmd $PID VM.command_line > $R/vm-cmdline.txt 2>&1
grep -i "open files" /proc/$PID/limits >> $R/vm-flags.txt
grep -o -E "native_transport_max_request_data_in_flight[a-z_]*=[^;]*;|native_transport_max_message_size=[^;]*;|in_select_cartesian_product[a-z_]*=[^;]*;|memtable_heap_space=[^;]*;|max_mutation_size=[^;]*;|native_transport_receive_queue_capacity=[^;]*;|memtable_allocation_type=[^;]*;|authenticator=[^;]*;|authorizer=[^;]*;|role_manager=[^;]*;|commitlog_segment_size=[^;]*;|native_transport_max_threads=[^;]*;|write_request_timeout=[^;]*;|native_transport_timeout=[^;]*;" $T/logs/system.log | sort -u > $R/resolved.txt
python3 -I $H/u7.py ddl > $R/ddl.txt 2>&1 || { log "INVALID: ddl failed"; kill $PID; }
python3 -I $H/u7.py settings > $R/settings.txt 2>&1
sleep 5   # permissions_validity 2 s
python3 -I $H/u7.py privcheck > $R/privcheck.txt 2>&1
log "privcheck: $(grep -c ' PASS ' $R/privcheck.txt) PASS, $(grep -c ' FAIL ' $R/privcheck.txt) FAIL"
setsid nohup python3 -I $H/victim.py $R/victim.csv $VSTOP 20 < /dev/null > $R/victim.err 2>&1 &
VP=$!; echo $VP > $R/victim.pid
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
sleep 60
log "baseline done (60 s, victim running)"
T0=$(date +%s); END=""; CAP=600; POST=120; OOMSEEN=""
oom_seen(){ [ -n "$OOMSEEN" ] && return; grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && { OOMSEEN=1; log "OOM line first seen in stdout"; }; }
oom_done(){ grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt || return 1
  grep -q "Heap dump file created" $R/stdout.txt || return 1
  return 0; }
post(){ log "OOM endpoint in step $1; daemon left up ${POST} s (victim after-view)"; for j in $(seq 1 $POST); do kill -0 $PID 2>/dev/null || { log "daemon exited during post wait"; break; }; sleep 1; done; }
for st in $STEPS; do
  IFS=: read kind p q k0 <<< "$st"
  kill -0 $PID 2>/dev/null || { log "daemon gone before step $st"; END="daemon-exit"; break; }
  log "step $st start (attacker u7atk)"
  python3 -I $H/u7.py send --kind $kind --p $p --q $q --k0 $k0 --user u7atk --out $R/client.txt >> $R/client.err 2>&1 &
  CP=$!
  while kill -0 $CP 2>/dev/null && kill -0 $PID 2>/dev/null; do
    sleep 1; oom_seen
    if [ $(( $(date +%s) - T0 )) -ge $CAP ]; then log "CAP ${CAP}s reached in step $st"; END="cap"; break; fi
    f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
    [ "$f" -lt 4096 ] && { log "DISK GUARD ${f}M"; END="disk-guard"; break; }
    if oom_done; then post $st; END="oom"; break; fi
  done
  [ -n "$END" ] && break
  if ! kill -0 $PID 2>/dev/null; then log "daemon gone during step $st"; END="daemon-exit"; sleep 3; kill $CP 2>/dev/null; break; fi
  if tail -1 $R/client.txt | grep -q -E "outcome=ERR (NoHostAvailable|ConnectionShutdown|OperationTimedOut|ConnectionException)"; then
    log "step $st client lost its connection: $(tail -1 $R/client.txt | cut -c1-160); waiting for daemon exit or cap"
    while kill -0 $PID 2>/dev/null; do
      sleep 2; oom_seen
      if [ $(( $(date +%s) - T0 )) -ge $CAP ]; then log "CAP ${CAP}s reached in step $st (daemon alive)"; END="cap"; break; fi
      if oom_done; then post $st; END="oom"; break; fi
    done
    [ -z "$END" ] && { log "daemon gone during step $st (after client loss)"; END="daemon-exit"; }
    break
  fi
  wait $CP
  log "step $st client done: $(tail -1 $R/client.txt)"
  sleep 15
  python3 -I $H/u7.py count --k $k0 >> $R/client.txt 2>&1
  python3 -I $H/u7.py count --k $(( k0 + p - 1 )) >> $R/client.txt 2>&1
  log "post-step victim watch ${POST} s"; sleep $POST
done
[ -z "$END" ] && END="survived"
if kill -0 $PID 2>/dev/null; then
  log "stopping daemon ($END)"
  kill $PID
  for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
fi
log "daemon stopped"
sleep 10   # victim records the stopped node
touch $VSTOP
for i in $(seq 1 20); do kill -0 $VP 2>/dev/null || break; sleep 1; done
kill $VP 2>/dev/null
pkill -f "$H/u7.py" 2>/dev/null
touch $STOP
sleep 3
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="OOM($END) oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/debug.log $T/logs/gc.log* $R/ 2>/dev/null
gzip -f $R/debug.log 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
python3 -I $H/victim-summary.py $R > $R/victim-summary.txt 2>&1
log "done"
