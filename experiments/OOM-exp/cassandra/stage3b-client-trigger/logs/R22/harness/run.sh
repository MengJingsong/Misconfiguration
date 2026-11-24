#!/bin/bash
# R22 3-b confirm (pc72, 2026-11-23), from the stage-2 run.sh. Changes: PasswordAuthenticator + CassandraAuthorizer +
# CassandraRoleManager in cassandra.yaml; the superuser (default cassandra role) only creates roles, the admin schema
# (r22.rt, r22.blob; vic.kv for the tenant) and grants (client.py setup); fill, hot and blob clients log in as role
# 'attacker' (MODIFY on r22.rt and r22.blob only); settings/clients read as role 'ops' (SELECT on system_views only);
# a victim tenant (role 'tenant', own keyspace vic) runs 5 writes/s + 5 reads/s from 60 s before the fill to 30 s after
# the W stop; fill stops at a fixed tombstone count (FILLN, default n:1231000 = stage 2's K0 count at 15,872 MiB);
# the heap dump is scanned with hprofhist.py and deleted; mode A = claim checks only (setup, preauth.py, authcheck).
# Paths /mydata/s4/3b-R22 (logs) and /dev/shm/3b-R22 (data, dumps; tmpfs as stage 2's E2).
# usage: bash run.sh <label> <heap 15872M|8G|512M> <arm T|C|I|D> <mode R|S|A> [wmax]
#   mode R (main): F to 0.45 x trigger (T/I/D batches of 1000 to pk=0, 1 in flight; C batches of 1000 round-robin over
#          1,000 partitions, <= 8 in flight), Q (10 s, L0, 20 s; arm I: setconcurrency MutationStage 1),
#          W = hot (bursts of 64 at W+0 and W+20, paced <= 16/s, <= 40 outstanding) + 3 blob clients (127.0.0.2/3/4, 4/3 per s
#          each, 12 MiB, <= 28 outstanding each, skip when full). T/D stop: node death, wmax (900) or 60 s after a r22.rt
#          switch; C/I stop: node death or wmax (= W_CI), a switch is recorded only.
#   mode S (S512): F to 0.75 x trigger (batches of 100, 1 in flight; C round-robin), W = hot only: burst 64 at W+0, then
#          <= 64 outstanding, <= 110/s, 150 s; T/D stop on a r22.rt switch, C/I record it. Arm D: histogram every 30 s of W.
# Launch detached: ( setsid nohup bash run.sh ... < /dev/null > /dev/null 2>&1 & ); progress in <run>/logs/driver.log,
# done marker <run>/DONE. Node under systemd-run --user --scope -p MemorySwapMax=0, taskset 24-31; data on /dev/shm/r22/<label>.
set -u
LABEL=$1; HEAP=$2; ARM=$3; MODE=$4
BASE=/mydata/s4/3b-R22; CASS=$BASE/cassandra; RUN=$BASE/$LABEL; SHM=/dev/shm/3b-R22/$LABEL; DUMP=/dev/shm/3b-R22/dump-$LABEL
FILLN=${FILLN:-n:1231000}; VICTIM_CPU=17
ATK="env R22_USER=attacker R22_PASS=atk-3b-R22"; OPS="env R22_USER=ops R22_PASS=ops-3b-R22"; TEN="env R22_USER=tenant R22_PASS=ten-3b-R22"
H=$(dirname "$(readlink -f "$0")")
NODE_CPUS=24-31; HOT_CPU=12; BLOB_CPUS=(13 14 15); POLL_CPU=16
SP=7710; SSLP=7711; NP=9742; JMX=7799
if [ "$MODE" = R ]; then FRAC=0.45; WMAX=${5:-900}; BATCH=1000; if [ "$ARM" = C ]; then FINF=8; else FINF=1; fi
else FRAC=0.75; WMAX=${5:-150}; BATCH=100; FINF=1; fi
rm -rf "$RUN" "$SHM" "$DUMP"; mkdir -p "$RUN"/{logs,hist} "$SHM"/{data,commitlog,hints,saved_caches,cdc_raw} "$DUMP"
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
col() { # value of column $1 in the last complete poll row
  tail -2 "$RUN/logs/poll.log" | awk -v h="$(head -1 "$RUN/logs/poll.log")" -v want="$1" 'BEGIN{n=split(h,a," "); for(i=1;i<=n;i++) if(a[i]==want) c=i} NF==n && $1 ~ /^[0-9]+$/ {v=$c} END{print v}'; }
log "start label=$LABEL heap=$HEAP arm=$ARM mode=$MODE frac=$FRAC batch=$BATCH fill_inflight=$FINF wmax=$WMAX"
ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | cut -c1-250 >> "$LOG"
free -m >> "$LOG"; df -m /dev/shm >> "$LOG"
HMB=$(python3 -I -c "import sys; v=sys.argv[1]; print(int(v[:-1])*(1024 if v[-1]=='G' else 1))" "$HEAP")
AVAIL=$(free -m | awk '/^Mem:/{print $7}'); SHMF=$(df -m --output=avail /dev/shm | tail -1)
if [ "$AVAIL" -lt $((HMB + 51200)) ] || [ "$SHMF" -lt 51200 ]; then log "resources short avail=$AVAIL shm=$SHMF, abort"; echo resources > "$RUN/DONE"; exit 1; fi
if ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | grep -q .; then log "another CassandraDaemon runs, abort"; echo othernode > "$RUN/DONE"; exit 1; fi
for p in $SP $SSLP $NP $JMX; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && { log "port $p busy, abort"; echo busy > "$RUN/DONE"; exit 1; }; done
cp -a "$CASS/conf" "$RUN/conf"
Y=$RUN/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 'r22-$LABEL'|" \
       -e "s|^storage_port:.*|storage_port: $SP|" -e "s|^ssl_storage_port:.*|ssl_storage_port: $SSLP|" \
       -e "s|^native_transport_port:.*|native_transport_port: $NP|" \
       -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"127.0.0.1:$SP\"|" \
       -e "s|^# hints_directory:.*|hints_directory: $SHM/hints|" \
       -e "s|^# commitlog_directory:.*|commitlog_directory: $SHM/commitlog|" \
       -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $SHM/cdc_raw|" \
       -e "s|^# saved_caches_directory:.*|saved_caches_directory: $SHM/saved_caches|" \
       -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
       -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
       -e "s|^role_manager: .*|role_manager: CassandraRoleManager|" "$Y"
grep -nE '^(authenticator|authorizer|role_manager|network_authorizer):' "$Y" >> "$LOG"
sed -i -e "s|^# data_file_directories:|data_file_directories:\n    - $SHM/data\n# (orig) data_file_directories:|" "$Y"
sed -i -e 's|^JMX_PORT="7199"|JMX_PORT="'$JMX'"|' "$RUN/conf/cassandra-env.sh"
echo "-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=$RUN/logs/gc.log:time,uptime,level,tags:filecount=50,filesize=20M" >> "$RUN/conf/jvm-server.options"
(cd "$CASS/conf" && diff -r . "$RUN/conf") > "$RUN/logs/conf.diff" 2>&1
export CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$DUMP \
       JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true"
( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 taskset -c $NODE_CPUS "$CASS/bin/cassandra" -f \
    < /dev/null > "$RUN/logs/stdout.txt" 2>&1 & )
ok=0
for i in $(seq 1 90); do
  sleep 2
  if ss -ltn | awk '{print $4}' | grep -q ":$NP\$"; then ok=1; break; fi
done
PID=$(ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | grep -F -- "-Dcassandra.logdir=$RUN/logs " | awk '{print $1}' | head -1)
[ -z "$PID" ] && PID=$(ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | grep -F -- "$RUN/logs" | awk '{print $1}' | head -1)
echo "$PID" > "$RUN/pid.txt"
log "native up=$ok pid=$PID"
CPIDS=""
stopnode() {
  [ -n "${POLLPID:-}" ] && kill "$POLLPID" 2>/dev/null
  [ -n "${RSSPID:-}" ] && kill "$RSSPID" 2>/dev/null
  for c in $CPIDS ${VPID:-}; do kill "$c" 2>/dev/null; done
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"; for i in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  fi
  log "node stopped"
}
if [ $ok -ne 1 ]; then log "node did not start"; stopnode; echo nostart > "$RUN/DONE"; rm -rf "$SHM" "$DUMP"; exit 1; fi
tr '\0' ' ' < /proc/$PID/cmdline > "$RUN/logs/cmdline.txt"
grep -o -- '-XX:MaxDirectMemorySize=[^ ]*\|-Xmx[^ ]*\|-XX:ParallelGCThreads=[^ ]*\|-XX:ConcGCThreads=[^ ]*\|-XX:HeapDumpPath=[^ ]*' "$RUN/logs/cmdline.txt" >> "$LOG"
jcmd $PID VM.flags > "$RUN/logs/vmflags.txt" 2>&1
grep -o 'ParallelGCThreads=[0-9]*\|ConcGCThreads=[0-9]*\|MaxDirectMemorySize=[0-9]*\|G1HeapRegionSize=[0-9]*' "$RUN/logs/vmflags.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
echo "jvm_cpus=$(taskset -cp $PID 2>/dev/null)" >> "$LOG"
( while kill -0 $PID 2>/dev/null; do echo "$(date +%s) $(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)"; sleep 1; done > "$RUN/logs/rss.log" 2>/dev/null & echo $! > "$RUN/rsspid" )
RSSPID=$(cat "$RUN/rsspid")
cd "$H"
( taskset -c $POLL_CPU java -cp "$BASE/classes" Poll $JMX 1000 > "$RUN/logs/poll.log" 2> "$RUN/logs/poll.err" & echo $! > "$RUN/pollpid" )
sleep 1; POLLPID=$(cat "$RUN/pollpid")
export CASSANDRA_HOME=$CASS
C="python3 -I $H/client.py"
taskset -c $HOT_CPU $C setup $NP > "$RUN/logs/setup.json" 2>> "$LOG"
cat "$RUN/logs/setup.json" >> "$LOG"
taskset -c $HOT_CPU $OPS $C settings $NP > "$RUN/logs/settings.json" 2>> "$LOG"
cat "$RUN/logs/settings.json" >> "$LOG"
if [ "$MODE" = A ]; then
  python3 -I "$H/preauth.py" 127.0.0.1 $NP > "$RUN/logs/preauth.txt" 2>&1
  taskset -c $HOT_CPU $C authcheck $NP > "$RUN/logs/authcheck.json" 2>> "$LOG"
  cat "$RUN/logs/preauth.txt" "$RUN/logs/authcheck.json" >> "$LOG"
  sleep 3; grep -iE 'batch|guardrail|unauthor' "$RUN/logs/system.log" "$RUN/logs/debug.log" | tail -30 > "$RUN/logs/authcheck-syslog.txt"
  stopnode; rm -rf "$SHM" "$DUMP"; log "authcheck done"; echo "authcheck" > "$RUN/DONE"; exit 0
fi
VSTOP=$RUN/STOPV
( taskset -c $VICTIM_CPU $TEN $C victim $NP 5 5 200 7200 "$VSTOP" "$RUN/logs/victim.csv" > "$RUN/logs/victim.json" 2> "$RUN/logs/victim.err" & echo $! > "$RUN/victimpid" )
sleep 1; VPID=$(cat "$RUN/victimpid"); log "victim started pid=$VPID"; sleep 60
TARGET=$FILLN
log "fill target $TARGET (fixed tombstone count, as attacker)"
sleep 2
log "fill start"
taskset -c $HOT_CPU $ATK $C fill $NP $ARM $TARGET "$RUN/logs/poll.log" $BATCH $FINF > "$RUN/logs/fill.json" 2>> "$LOG"
cat "$RUN/logs/fill.json" >> "$LOG"
I0=$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['I0'])" "$RUN/logs/fill.json" 2>/dev/null)
if [ -z "$I0" ]; then log "fill failed"; stopnode; echo fillfail > "$RUN/DONE"; rm -rf "$SHM" "$DUMP"; exit 1; fi
log "quiesce"; sleep 10
jcmd $PID GC.class_histogram > "$RUN/hist/L0.txt" 2>&1; log "L0 done"
sleep 20
if [ "$ARM" = I ]; then
  "$CASS/bin/nodetool" -p $JMX setconcurrency MutationStage 1 >> "$LOG" 2>&1
  "$CASS/bin/nodetool" -p $JMX getconcurrency MutationStage >> "$LOG" 2>&1
fi
if [ "$ARM" = D ]; then
  ( k=0; while [ ! -f "$RUN/WDONE" ] && [ $k -lt 30 ]; do sleep 30; [ -f "$RUN/WDONE" ] && break; k=$((k+1));
      kill -0 $PID 2>/dev/null || break
      jcmd $PID GC.class_histogram > "$RUN/hist/D$(printf %02d $k)-$(date +%s).txt" 2>&1; done ) &
fi
SW0=$(col sw_rt)
log "W start I0=$I0 sw_rt0=$SW0"
WSTART=$(date +%s)
WHY=""; SWAT=""; ENTRY=""
STOPF=$RUN/STOPW
if [ "$MODE" = R ]; then
  ( taskset -c $HOT_CPU $ATK $C hot $NP $ARM $I0 16 40 64 0,20 $((WMAX + 5)) "$STOPF" "$RUN/logs/hot.csv" "$RUN/logs/hot-resp.csv" > "$RUN/logs/hot.json" 2>> "$RUN/logs/hot.err" & echo $! > "$RUN/hotpid" )
  for j in 0 1 2; do
    ( taskset -c ${BLOB_CPUS[$j]} $ATK $C blob $NP 127.0.0.$((j + 2)) $((j + 2)) 1.3333333 28 $((WMAX + 5)) "$STOPF" "$RUN/logs/blob$j.csv" "$RUN/logs/blob$j-resp.csv" > "$RUN/logs/blob$j.json" 2>> "$RUN/logs/blob$j.err" & echo $! > "$RUN/blob${j}pid" )
  done
  sleep 0.5; CPIDS="$(cat "$RUN/hotpid") $(cat "$RUN/blob0pid") $(cat "$RUN/blob1pid") $(cat "$RUN/blob2pid")"
else
  ( taskset -c $HOT_CPU $ATK $C hot $NP $ARM $I0 110 64 64 0 $((WMAX + 5)) "$STOPF" "$RUN/logs/hot.csv" "$RUN/logs/hot-resp.csv" > "$RUN/logs/hot.json" 2>> "$RUN/logs/hot.err" & echo $! > "$RUN/hotpid" )
  sleep 0.5; CPIDS="$(cat "$RUN/hotpid")"
fi
log "clients $CPIDS"
while true; do
  sleep 1
  EL=$(( $(date +%s) - WSTART ))
  if ! kill -0 $PID 2>/dev/null; then WHY="node death"; break; fi
  if [ $EL -ge $WMAX ]; then WHY="wmax"; break; fi
  if [ -z "$ENTRY" ] && [ $EL -ge 40 ] && [ "$MODE" = R ]; then
    ENTRY="active=$(col active) pending=$(col pending)"; log "entry check W+40: $ENTRY"
    taskset -c $HOT_CPU $OPS $C clients $NP >> "$LOG" 2>&1
    ss -tn | awk '$5 ~ /:9742$/ {split($4,a,":"); print a[1]}' | sort | uniq -c | tr '\n' ';' >> "$LOG"; echo >> "$LOG"
  fi
  SW=$(col sw_rt)
  if [ -z "$SWAT" ] && [ -n "$SW" ] && [ -n "$SW0" ] && [ "$SW" -gt "$SW0" ] 2>/dev/null; then
    SWAT=$EL; log "r22.rt switch at W+$EL ($SW0 -> $SW)"
    if [ "$MODE" = S ] && { [ "$ARM" = T ] || [ "$ARM" = D ]; }; then WHY="rt switch at W+$EL"; break; fi
  fi
  if [ -n "$SWAT" ] && [ "$MODE" = R ] && { [ "$ARM" = T ] || [ "$ARM" = D ]; } && [ $((EL - SWAT)) -ge 60 ]; then WHY="60 s after rt switch at W+$SWAT"; break; fi
  # hung rule: no JMX sample for 180 s and GC log silent for 180 s
  PM=$(stat -c %Y "$RUN/logs/poll.log" 2>/dev/null || echo 0); GM=$(stat -c %Y "$RUN/logs/gc.log" 2>/dev/null || echo 0); NOW=$(date +%s)
  if [ $((NOW - PM)) -ge 180 ] && [ $((NOW - GM)) -ge 180 ]; then
    jcmd $PID Thread.print > "$RUN/logs/hung-threads.txt" 2>&1; kill -9 $PID; WHY="hung"; break
  fi
  alive=0; for c in $CPIDS; do kill -0 $c 2>/dev/null && alive=1; done
  if [ $alive -eq 0 ]; then WHY="clients ended"; break; fi
done
log "W stop: $WHY after $(( $(date +%s) - WSTART )) s"
touch "$STOPF"
for i in $(seq 1 50); do alive=0; for c in $CPIDS; do kill -0 $c 2>/dev/null && alive=1; done; [ $alive -eq 0 ] && break; sleep 1; done
for c in $CPIDS; do kill $c 2>/dev/null; done
for f in hot blob0 blob1 blob2; do [ -f "$RUN/logs/$f.json" ] && cat "$RUN/logs/$f.json" >> "$LOG"; done
touch "$RUN/WDONE"
WEND=$(date +%s)
sleep 5
if kill -0 "$PID" 2>/dev/null; then jcmd $PID GC.class_histogram > "$RUN/hist/L1.txt" 2>&1; log "L1 done"; ALIVE=1; else log "node DEAD after W"; ALIVE=0; fi
sleep 3
while [ $(( $(date +%s) - WEND )) -lt 30 ]; do sleep 1; done
touch "$VSTOP"; for i in $(seq 1 25); do kill -0 "$VPID" 2>/dev/null || break; sleep 1; done; kill "$VPID" 2>/dev/null; log "victim stopped"
stopnode
# wait for a heap dump still being written by a dying JVM (kill -9 runs after the dump)
for i in $(seq 1 120); do ps -eo pid,comm,args | awk '$2=="java"' | grep -qF -- "cassandra.logdir=$RUN/logs" || break; sleep 1; done
grep -nF 'java.lang.OutOfMemoryError' "$RUN/logs/system.log" "$RUN/logs/stdout.txt" 2>/dev/null | grep -v 'JVM Arguments' > "$RUN/logs/oom-grep.txt"
grep -h 'Enqueuing flush of' "$RUN/logs/system.log" "$RUN/logs/debug.log" 2>/dev/null | sort -u > "$RUN/logs/flushes.txt"
ls -la "$DUMP" >> "$LOG" 2>/dev/null
du -sh "$SHM" >> "$LOG" 2>/dev/null
rm -rf "$SHM"
for f in "$DUMP"/*.hprof; do
  [ -f "$f" ] || continue
  log "dump scan start: $(basename "$f") $(stat -c %s "$f")"
  nice -n 19 ionice -c 3 taskset -c 0-3 python3 -I "$H/hprofhist.py" "$f" 40 > "$RUN/hist/hprof-hist.txt" 2>&1
  log "dump scanned; deleted: $(basename "$f")"; rm -f "$f"
done
rm -rf "$DUMP"
log "done alive=$ALIVE why=$WHY switch_at=$SWAT entry=$ENTRY"
echo "alive=$ALIVE why=$WHY switch_at=$SWAT" > "$RUN/DONE"
