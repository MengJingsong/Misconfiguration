#!/bin/bash
# B23 stage 3-b confirm run driver (adapted from the stage-2 harness/run.sh). usage: bash run3b.sh <label> <topo vnode|single> <n1-heap e.g. 2G> <N> [size=64000] [inflight=200]
# Changes from stage 2 (run.sh): authentication on (PasswordAuthenticator + CassandraAuthorizer + CassandraRoleManager) on all three
#   instances; system_auth RF 3 (+ full repair) so a login survives n3 being down; schema made by the superuser; the attack is
#   B23Client "attack" as role 'attacker' (MODIFY on app.data only) through n1, with partition keys chosen client-side off n1
#   (topo vnode: num_tokens 16 as shipped, no initial_token; topo single: the stage-2 placement E2); a victim role 'victim'
#   (SELECT+MODIFY on vks.t only) runs a steady 100 req/s (50 W + 50 R, 100 B) through n1 from 60 s before n3 stops to 60 s
#   after the endpoint. Pollers, stop rules, dumps as stage 2 (no 13:15 cutoff; per-case 4 h cap kept by the session).
# Topology as stage 2: n1 127.0.0.31 (victim coordinator, JMX 7231, data/commitlog/hints on /mydata, heap <n1-heap>),
#   n2 127.0.0.32 (seed, JMX 7232, 8G, /dev/shm), n3 127.0.0.33 (JMX 7233, 8G, /dev/shm; stopped by the operator before the attack).
set -u
LABEL=$1; TOPO=$2; HEAP=$3; N=$4; SIZE=${5:-64000}; INFL=${6:-200}
BASE=/mydata/s4/3b-B23; ORIG=/mydata/s4/cassandra-base
RUN=$BASE/$LABEL; SHM=/dev/shm/3b-B23/$LABEL; DUMP=$RUN/dump
H=$BASE/harness; LIB=$ORIG/lib
CCP="$BASE/classes:$LIB/cassandra-driver-core-3.12.1-shaded.jar:$LIB/guava-32.0.1-jre.jar:$LIB/slf4j-api-2.0.17.jar:$LIB/failureaccess-1.0.1.jar"
CLI="java -Xmx4g -cp $CCP B23Client"
rm -rf "$RUN" "$SHM"; mkdir -p "$RUN/logs" "$DUMP" "$SHM"
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
col() { tail -2 "$RUN/logs/poll1.log" 2>/dev/null | awk -v h="$(head -1 "$RUN/logs/poll1.log" 2>/dev/null)" -v want="$1" 'BEGIN{n=split(h,a," "); for(i=1;i<=n;i++) if(a[i]==want) c=i} NF==n && $1 ~ /^[0-9]+$/ {v=$c} END{print v}'; }
log "start label=$LABEL topo=$TOPO n1heap=$HEAP N=$N size=$SIZE inflight=$INFL"
if ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | grep -q .; then log "another CassandraDaemon runs, abort"; echo othernode > "$RUN/DONE"; exit 1; fi
free -m >> "$LOG"; df -m /dev/shm /mydata >> "$LOG"
ADDR=(x 127.0.0.31 127.0.0.32 127.0.0.33); TOK=(x 0 -2 -1); JMX=(x 7231 7232 7233)
declare -A PID
for i in 1 2 3; do
  if [ $i = 1 ]; then D=$RUN/n1; else D=$SHM/n$i; fi
  mkdir -p "$RUN/n$i/logs" "$D"/{data,commitlog,hints,saved_caches,cdc_raw}
  cp -a "$ORIG/conf" "$RUN/n$i/conf"; Y=$RUN/n$i/conf/cassandra.yaml
  sed -i -e "s|^cluster_name:.*|cluster_name: '3b-b23-$LABEL'|" \
         -e "s|^listen_address:.*|listen_address: ${ADDR[$i]}|" -e "s|^rpc_address:.*|rpc_address: ${ADDR[$i]}|" \
         -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"127.0.0.32:7000\"|" \
         -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
         -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
         -e "s|^role_manager:.*|role_manager: CassandraRoleManager|" \
         -e "s|^# hints_directory:.*|hints_directory: $D/hints|" \
         -e "s|^# commitlog_directory:.*|commitlog_directory: $D/commitlog|" \
         -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $D/cdc_raw|" \
         -e "s|^# saved_caches_directory:.*|saved_caches_directory: $D/saved_caches|" "$Y"
  if [ "$TOPO" = single ]; then sed -i -e "s|^num_tokens:.*|num_tokens: 1|" -e "s|^# initial_token:.*|initial_token: ${TOK[$i]}|" "$Y"; fi
  sed -i -e "s|^# data_file_directories:|data_file_directories:\n    - $D/data\n# (orig) data_file_directories:|" "$Y"
  sed -i -e 's|^JMX_PORT="7199"|JMX_PORT="'${JMX[$i]}'"|' "$RUN/n$i/conf/cassandra-env.sh"
  echo "-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=$RUN/n$i/logs/gc.log:time,uptime,level,tags:filecount=50,filesize=20M" >> "$RUN/n$i/conf/jvm-server.options"
  (cd "$ORIG/conf" && diff -r . "$RUN/n$i/conf") > "$RUN/n$i/logs/conf.diff" 2>&1
done
startnode() { # $1 = node index
  local i=$1 HP=8G HD=$SHM/dump-n$1
  if [ $i = 1 ]; then HP=$HEAP; HD=$DUMP; fi
  mkdir -p "$HD"
  ( export CASSANDRA_CONF=$RUN/n$i/conf CASSANDRA_LOG_DIR=$RUN/n$i/logs MAX_HEAP_SIZE=$HP CASSANDRA_HEAPDUMP_DIR=$HD \
      JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true"
    ulimit -n 1048576 2>/dev/null
    setsid nohup systemd-run --user --scope -p MemorySwapMax=0 "$ORIG/bin/cassandra" -f < /dev/null > "$RUN/n$i/logs/stdout.txt" 2>&1 & )
  local ok=0
  for k in $(seq 1 120); do sleep 2
    if ss -ltn | awk '{print $4}' | grep -qF "${ADDR[$i]}:9042"; then ok=1; break; fi
    ps -eo comm,args | awk '$1=="java"' | grep -qF -- "-Dcassandra.logdir=$RUN/n$i/logs" || [ $k -lt 5 ] || break
  done
  PID[$i]=$(ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | grep -F -- "-Dcassandra.logdir=$RUN/n$i/logs" | awk '{print $1}' | head -1)
  log "n$i native up=$ok pid=${PID[$i]}"; echo "${PID[$i]}" > "$RUN/n$i/pid.txt"
  [ $ok = 1 ]
}
VPID=""
stopall() {
  log "stopall begin (teardown)"; touch "$RUN/victim.stop"
  for p in ${BGP:-} ${APID:-}; do kill "$p" 2>/dev/null; done
  for i in 1 2 3; do
    p=${PID[$i]:-}; [ -z "$p" ] && continue
    if kill -0 "$p" 2>/dev/null; then kill "$p"; for k in $(seq 1 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -0 "$p" 2>/dev/null && kill -9 "$p"; fi
  done
  if [ -n "$VPID" ]; then for k in $(seq 1 20); do kill -0 $VPID 2>/dev/null || break; sleep 1; done; kill -9 $VPID 2>/dev/null; fi
  log "all nodes and clients stopped"
}
fail() { log "FAIL: $*"; stopall; echo "fail: $*" > "$RUN/DONE"; rm -rf "$SHM"; rm -rf "$RUN"/n1/{data,commitlog,hints,saved_caches,cdc_raw}; exit 1; }
startnode 2 || fail "n2 start"
startnode 3 || fail "n3 start"
startnode 1 || fail "n1 start"
NT="$ORIG/bin/nodetool -h 127.0.0.1"
for k in $(seq 1 30); do $NT -p 7231 status > "$RUN/logs/status-up.txt" 2>&1; [ "$(grep -c '^UN' "$RUN/logs/status-up.txt")" = 3 ] && break; sleep 2; done
cat "$RUN/logs/status-up.txt" >> "$LOG"
[ "$(grep -c '^UN' "$RUN/logs/status-up.txt")" = 3 ] || fail "not 3 UN"
P1=${PID[1]}
tr '\0' ' ' < /proc/$P1/cmdline > "$RUN/logs/n1-cmdline.txt"
grep -o -- '-XX:MaxDirectMemorySize=[^ ]*\|-Xmx[^ ]*\|-Xms[^ ]*\|-XX:HeapDumpPath=[^ ]*\|-XX:+Use[A-Za-z0-9]*GC' "$RUN/logs/n1-cmdline.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
jcmd $P1 VM.flags > "$RUN/logs/n1-vmflags.txt" 2>&1
grep -o 'MaxDirectMemorySize=[0-9]*\|MaxHeapSize=[0-9]*\|G1HeapRegionSize=[0-9]*\|ParallelGCThreads=[0-9]*' "$RUN/logs/n1-vmflags.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
cat /proc/$P1/cgroup >> "$LOG"
grep -h -E '^(authenticator|authorizer|role_manager|num_tokens|initial_token):' "$RUN/n1/conf/cassandra.yaml" >> "$LOG"
# --- superuser: wait for the default role, system_auth RF 3 + repair, roles, schema, grants
echo "SELECT release_version FROM system.local;" > "$RUN/ping.cql"
for k in $(seq 1 60); do $CLI admin 127.0.0.31 cassandra cassandra "$RUN/ping.cql" > "$RUN/logs/ping.txt" 2>&1 && grep -q '   OK' "$RUN/logs/ping.txt" && break; sleep 2; done
grep -q '   OK' "$RUN/logs/ping.txt" || fail "superuser login"
log "superuser login ok"
$CLI admin 127.0.0.31 cassandra cassandra "$H/admin1.cql" > "$RUN/logs/admin1.txt" 2>&1
$NT -p 7231 repair -full system_auth > "$RUN/logs/repair-system_auth.txt" 2>&1; log "repair system_auth rc=$?"
$CLI admin 127.0.0.31 cassandra cassandra "$H/admin2.cql" > "$RUN/logs/admin2.txt" 2>&1
grep -c ERROR "$RUN/logs/admin1.txt" "$RUN/logs/admin2.txt" >> "$LOG"
$CLI admin 127.0.0.31 attacker atk-pw-3b "$H/probe-attacker.cql" > "$RUN/logs/probe-attacker.txt" 2>&1
log "attacker probe: $(grep -c '   OK' $RUN/logs/probe-attacker.txt) OK, $(grep -c '   ERROR' $RUN/logs/probe-attacker.txt) ERROR"
# --- victim from here on
( setsid nohup $CLI victim 127.0.0.31 victim vic-pw-3b 127.0.0.51 100 "$RUN/logs/victim.log" "$RUN/victim.stop" < /dev/null > "$RUN/logs/victim.err" 2>&1 & )
sleep 2; VPID=$(ps -eo pid,args | grep -F "B23Client victim" | grep -F "$RUN/logs/victim.log" | grep -v grep | awk '{print $1}' | head -1); log "victim pid $VPID"
cd "$H"
( java -cp "$BASE/classes" Poll 7231 1000 > "$RUN/logs/poll1.log" 2> "$RUN/logs/poll1.err" & echo $! > "$RUN/pp1" )
( java -cp "$BASE/classes" Poll 7232 1000 > "$RUN/logs/poll2.log" 2> "$RUN/logs/poll2.err" & echo $! > "$RUN/pp2" )
( while kill -0 $P1 2>/dev/null; do echo "$(date +%s.%N | cut -c1-14) $(du -sb $RUN/n1/hints 2>/dev/null | cut -f1) $(awk '/RssAnon/{print $2}' /proc/$P1/status 2>/dev/null)"; sleep 1; done > "$RUN/logs/hints-rss.log" 2>/dev/null & echo $! > "$RUN/pp3" )
( while true; do echo "$(date +%s) $(df -m --output=used /dev/shm | tail -1)"; sleep 5; done > "$RUN/logs/shm.log" & echo $! > "$RUN/pp4" )
sleep 3
BGP="$(cat $RUN/pp1) $(cat $RUN/pp2) $(cat $RUN/pp3) $(cat $RUN/pp4)"
log "MaxHintsInProgress: $(grep MaxHintsInProgress $RUN/logs/poll1.err)"
log "victim baseline, all up (30 s)"; sleep 30
log "operator: stopping n3 (nodetool stopdaemon)"
$NT -p 7233 stopdaemon >> "$LOG" 2>&1
for k in $(seq 1 30); do kill -0 ${PID[3]} 2>/dev/null || break; sleep 1; done
kill -0 ${PID[3]} 2>/dev/null && { log "n3 still alive, SIGTERM"; kill ${PID[3]}; sleep 10; kill -9 ${PID[3]} 2>/dev/null; }
for k in $(seq 1 30); do $NT -p 7231 status 2>/dev/null | grep -q '^DN *127.0.0.33' && break; sleep 1; done
$NT -p 7231 status > "$RUN/logs/status-down.txt" 2>&1; cat "$RUN/logs/status-down.txt" >> "$LOG"
grep -q '^DN *127.0.0.33' "$RUN/logs/status-down.txt" || fail "n3 not DN at n1"
log "victim baseline, n3 down (30 s)"; sleep 30
log "n1 hints dir before load: $(du -sb $RUN/n1/hints | cut -f1) B, files $(ls $RUN/n1/hints | wc -l)"
LSTART=$(date +%s); log "attack start N=$N (role attacker, keys chosen off n1)"
( $CLI attack 127.0.0.31 attacker atk-pw-3b 127.0.0.41 $N $INFL $SIZE app.data 127.0.0.31 "$RUN/logs/attack.log" > "$RUN/logs/attack-stdout.txt" 2>&1 & echo $! > "$RUN/apid" )
sleep 0.5; APID=$(cat "$RUN/apid"); log "attack pid $APID"
WHY=""; SDONE=""; VALID=1
while true; do
  sleep 1; NOW=$(date +%s); EL=$((NOW - LSTART))
  if ! kill -0 $P1 2>/dev/null; then WHY="n1 death at L+$EL"; break; fi
  if ! kill -0 ${PID[2]} 2>/dev/null; then WHY="n2 death at L+$EL"; VALID=0; break; fi
  if [ $EL -ge 600 ]; then WHY="600 s cap"; break; fi
  SU=$(tail -1 "$RUN/logs/shm.log" | awk '{print $2}'); if [ -n "$SU" ] && [ "$SU" -gt 57344 ]; then WHY="tmpfs > 56 GiB at L+$EL"; VALID=0; break; fi
  K=$(col K)
  if ! kill -0 $APID 2>/dev/null && [ -z "$SDONE" ]; then SDONE=$EL; log "attack client done at L+$EL K=$K"; fi
  # amendment after R1 (2026-11-23): once n1 has thrown OutOfMemoryError, wait for the JVM's own heap dump + exit (to the 600 s cap)
  if [ -n "$SDONE" ] && [ $((EL - SDONE)) -ge 60 ]; then
    if grep -q 'java.lang.OutOfMemoryError' "$RUN/n1/logs/stdout.txt" 2>/dev/null; then [ -z "${OOMW:-}" ] && { OOMW=$EL; log "OOM in n1 stdout at check L+$EL, JVM alive: waiting for its own dump + exit (to the 600 s cap)"; }
    else WHY="attack done + 60 s"; break; fi
  fi
  PM=$(stat -c %Y "$RUN/logs/poll1.log" 2>/dev/null || echo 0); GM=$(stat -c %Y "$RUN/n1/logs/gc.log" 2>/dev/null || echo 0)
  if [ $((NOW - PM)) -ge 180 ] && [ $((NOW - GM)) -ge 180 ]; then jstack $P1 > "$RUN/logs/hung-threads.txt" 2>&1; kill -9 $P1; WHY="hung"; break; fi
  [ $((EL % 10)) = 0 ] && log "L+$EL K=$K pending=$(col mut_pending) old=$(col old) unavail=$(col unavail) wr_done=$(col wr_done)"
done
log "stop: $WHY valid=$VALID"
kill $APID 2>/dev/null
kill -0 $P1 2>/dev/null && ALIVE=1 || ALIVE=0
log "victim after-window (60 s)"; sleep 60
stopall
for k in $(seq 1 180); do ps -eo comm,args | awk '$1=="java"' | grep -qF -- "-Dcassandra.logdir=$RUN/n1/logs" || break; sleep 1; done
grep -nF 'java.lang.OutOfMemoryError' "$RUN/n1/logs/system.log" "$RUN/n1/logs/stdout.txt" 2>/dev/null | grep -v 'JVM Arguments' > "$RUN/logs/oom-grep.txt"
log "OOM lines: $(wc -l < $RUN/logs/oom-grep.txt); first: $(head -1 $RUN/logs/oom-grep.txt | cut -c1-300)"
log "n1 hints dir at end: $(du -sb $RUN/n1/hints | cut -f1) B; n1 data $(du -sb $RUN/n1/data | cut -f1) B; shm $(du -sb $SHM | cut -f1) B"
ls -la "$DUMP" >> "$LOG"
if ls "$DUMP"/*.hprof > /dev/null 2>&1; then ( setsid nohup bash $H/dumpproc.sh "$RUN" 0 < /dev/null > /dev/null 2>&1 & ); log "dump analysis started (dump deleted after)"; fi
rm -rf "$SHM" "$RUN"/n1/{data,commitlog,hints,saved_caches,cdc_raw}
log "done alive=$ALIVE why=$WHY valid=$VALID"
echo "alive=$ALIVE why=$WHY valid=$VALID" > "$RUN/DONE"
