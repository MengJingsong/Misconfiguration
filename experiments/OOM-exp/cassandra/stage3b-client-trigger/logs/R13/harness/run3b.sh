#!/usr/bin/env bash
# R13 stage 3-b confirm run driver (2026-11-23), from the case's harness/run.sh (stage 2).
# Usage: run3b.sh <run-id> <mode> <N> <hold-s> [ips]
#   mode A  : pre-auth, arm P (15.8 MB multi-frame v5 BATCH), random statement id, reconnect on close   (3-b claim as written)
#   mode PF : pre-auth, arm PS (130,881 B single-frame BATCH), random id, 32 pipelined per connection    (pre-auth, small frames)
#   mode L  : LOGIN role "attacker" with no GRANT, arm P, random statement id                             (lowest authenticated)
#   ips     : number of client source addresses (default: one per connection)
# Layout: $W/cassandra (cp -a of /mydata/s4/cassandra-base, shipped conf/ untouched), $W/conf-auth (shipped conf/ with
# authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer; role_manager ships CassandraRoleManager),
# $W/harness, $W/runs/<run-id>. Heap 2 GiB (V7 as the verified arm), direct auto, no container limit, swap 0 for the daemon.
# Per run: fresh data/ and logs/ -> start -> superuser creates roles victim (+ attacker in mode L), keyspace victim, table
# victim.kv, GRANT SELECT, MODIFY ON victim.kv TO victim -> monitors + victim workload -> 30 s baseline -> attack -> endpoint
# or hold end -> 30 s "after" for the victim -> stop everything -> copy logs -> summaries.
set -u
W=/mydata/s4/3b-R13; H=$W/harness; T=$W/cassandra; CONF=$W/conf-auth; HEAP=2G
RID=$1; MODE=$2; N=$3; HOLD=$4; IPS=${5:-0}
R=$W/runs/$RID; STOP=$R/STOP; VSTOP=$R/VSTOP
VPW=victim-pw-3b; APW=attacker-pw-3b
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T%z) $*"; }
ems(){ date +%s%3N; }
dpid(){ ps -eo pid=,comm=,args= | awk '$2=="java" && /CassandraDaemon/ {print $1}' | head -1; }
CQ(){ timeout 60 $T/bin/cqlsh 127.0.0.1 9042 "$@"; }
log "run $RID mode=$MODE N=$N hold=$HOLD ips=${IPS:-own} heap=$HEAP"
[ -n "$(dpid)" ] && { log "ABORT: a CassandraDaemon runs"; exit 1; }
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge 10 ] || { log "ABORT: /mydata free ${free}G < 10G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $CONF/cassandra.yaml $CONF/jvm11-server.options $CONF/cassandra-env.sh > $R/conf-md5.txt
diff $T/conf/cassandra.yaml $CONF/cassandra.yaml > $R/conf-diff.txt
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; exec env CASSANDRA_CONF=$CONF MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=3b-r13-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
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
grep -o -E "authenticator=[^;]*;|authorizer=[^;]*;|role_manager=[^;]*;|network_authorizer=[^;]*;|native_transport_max_request_data_in_flight[a-z_]*=[^;]*;|native_transport_max_message_size=[^;]*;|native_transport_receive_queue_capacity=[^;]*;|native_transport_max_concurrent_connections[a-z_]*=[^;]*;|native_transport_rate_limiting_enabled=[^;]*;|consecutive_message_errors_threshold=[^;]*;|batch_size_fail_threshold=[^;]*;" $T/logs/system.log | sort -u > $R/resolved.txt
java -cp $H Jmx 7199 get org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytes \
  org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytesPerIp >> $R/resolved.txt 2>&1
# superuser setup (default role cassandra/cassandra is created a few seconds after start)
for i in $(seq 1 45); do CQ -u cassandra -p cassandra -e "LIST ROLES" > /dev/null 2>&1 && break; sleep 2; done
{
  echo "== superuser statements (cqlsh as cassandra)"
  S="CREATE ROLE victim WITH PASSWORD = '$VPW' AND LOGIN = true;
CREATE KEYSPACE victim WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE victim.kv (k int PRIMARY KEY, v text);
GRANT SELECT ON TABLE victim.kv TO victim;
GRANT MODIFY ON TABLE victim.kv TO victim;"
  [ "$MODE" = L ] && S="$S
CREATE ROLE attacker WITH PASSWORD = '$APW' AND LOGIN = true;"
  echo "$S"
  CQ -u cassandra -p cassandra -e "$S" && echo "== setup OK"
  echo "== LIST ROLES"; CQ -u cassandra -p cassandra -e "LIST ROLES"
  echo "== LIST ALL PERMISSIONS OF victim"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF victim"
  if [ "$MODE" = L ]; then
    echo "== LIST ALL PERMISSIONS OF attacker"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF attacker"
    echo "== attacker negative checks (expect Unauthorized)"
    CQ -u attacker -p $APW -e "SELECT * FROM victim.kv LIMIT 1" 2>&1 | tail -2
    CQ -u attacker -p $APW -e "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}" 2>&1 | tail -2
  fi
  echo "== keyspaces (no r13 schema exists)"; CQ -u cassandra -p cassandra -e "DESCRIBE KEYSPACES"
  echo "== unauthenticated cqlsh (expect AuthenticationFailed)"; CQ -e "SELECT now() FROM system.local" 2>&1 | tail -1
} > $R/auth-setup.txt 2>&1
grep -q "== setup OK" $R/auth-setup.txt || { log "INVALID: auth setup failed"; kill $PID; exit 1; }
log "auth setup done"
setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
setsid nohup python3 -I $H/victim.py --user victim --pw $VPW --rate 10 --out $R/victim.txt --stop $VSTOP --src 127.0.0.1 < /dev/null > $R/victim.err 2>&1 &
VP=$!
sleep 30
case $MODE in
  A)  CARGS="--arm P --auth preauth --fake-id --reconnect" ;;
  PF) CARGS="--arm PS --auth preauth --fake-id --depth 32" ;;
  L)  CARGS="--arm P --auth login:attacker:$APW --fake-id" ;;
  *)  log "ABORT: mode $MODE"; kill $PID; exit 1 ;;
esac
log "baseline done; attack start N=$N mode=$MODE at_ms $(ems)"
P=$(( (N + 7) / 8 )); CP=""
for p in $(seq 0 $((P - 1))); do
  s=$(( p * 8 )); n=$(( N - s < 8 ? N - s : 8 ))
  python3 -I $H/client3b.py $CARGS --ips $IPS --conn-start $s --conn-n $n --hold-s $HOLD --out $R --tag p$p > $R/client-p$p.err 2>&1 &
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
  log "attack clients ended; daemon alive (hold end) at_ms $(ems) $DISK"
  for c in $CP; do wait $c 2>/dev/null; done
  log "victim after-phase (30 s, node alive)"; sleep 30; touch $VSTOP
  if grep -q "Dumping heap to" $R/stdout.txt && ! grep -q "Heap dump file created" $R/stdout.txt; then
    log "dump in progress at hold end: waiting (<= 600 s)"
    for i in $(seq 1 600); do grep -q "Heap dump file created" $R/stdout.txt && break; kill -0 $PID 2>/dev/null || break; sleep 1; done
    for i in $(seq 1 30); do kill -0 $PID 2>/dev/null || break; sleep 1; done
  fi
  if kill -0 $PID 2>/dev/null; then
    kill $PID
    for i in $(seq 1 60); do kill -0 $PID 2>/dev/null || break; sleep 1; done
    kill -0 $PID 2>/dev/null && { log "kill -9"; kill -9 $PID; }
  fi
  END="hold $DISK"
else
  log "daemon gone while attack running at_ms $(ems)"
  END=daemon-exit
  sleep 3; for c in $CP; do kill $c 2>/dev/null; done
  log "victim after-phase (30 s, node down)"; sleep 30; touch $VSTOP
fi
for c in $CP; do wait $c 2>/dev/null; done
touch $STOP $VSTOP
sleep 3
kill $VP 2>/dev/null
for i in $(seq 1 30); do systemctl --user is-active 3b-r13-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/debug.log* $T/logs/gc.log* $R/ 2>/dev/null
sleep 6
python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
python3 -I $H/victim_summary.py $R > $R/victim-summary.txt 2>&1
python3 -I $H/oomtime.py $R > $R/oomtime.txt 2>&1
log "done"
