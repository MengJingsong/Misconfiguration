#!/bin/bash
# R22 stage-2 run driver (from R17's run.sh; design §2.5). usage: bash run.sh <label> <heap 15872M|8G|512M> <arm T|C|I|D> <mode R|S> [wmax]
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
BASE=/mydata/s4/r22; CASS=$BASE/cassandra; RUN=$BASE/$LABEL; SHM=/dev/shm/r22/$LABEL; DUMP=/dev/shm/r22/dump-$LABEL
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
       -e "s|^# saved_caches_directory:.*|saved_caches_directory: $SHM/saved_caches|" "$Y"
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
  for c in $CPIDS; do kill "$c" 2>/dev/null; done
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
taskset -c $HOT_CPU $C schema $NP >> "$LOG" 2>&1
taskset -c $HOT_CPU $C settings $NP > "$RUN/logs/settings.json" 2>> "$LOG"
cat "$RUN/logs/settings.json" >> "$LOG"
TARGET=$(python3 -I - "$RUN/logs/settings.json" "$FRAC" <<'EOF'
import json, sys, re
s = json.load(open(sys.argv[1])); frac = float(sys.argv[2])
def b(v):
    m = re.match(r'([0-9.]+)\s*([KMG]i?B)?', v); x = float(m.group(1)); u = (m.group(2) or 'B')[0]
    return x * {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'B': 1}[u]
print(int(frac * float(s['memtable_cleanup_threshold']) * b(s['memtable_heap_space'])))
EOF
)
log "fill target K=$TARGET"
sleep 2
taskset -c $HOT_CPU $C fill $NP $ARM $TARGET "$RUN/logs/poll.log" $BATCH $FINF > "$RUN/logs/fill.json" 2>> "$LOG"
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
  ( taskset -c $HOT_CPU $C hot $NP $ARM $I0 16 40 64 0,20 $((WMAX + 5)) "$STOPF" "$RUN/logs/hot.csv" "$RUN/logs/hot-resp.csv" > "$RUN/logs/hot.json" 2>> "$RUN/logs/hot.err" & echo $! > "$RUN/hotpid" )
  for j in 0 1 2; do
    ( taskset -c ${BLOB_CPUS[$j]} $C blob $NP 127.0.0.$((j + 2)) $((j + 2)) 1.3333333 28 $((WMAX + 5)) "$STOPF" "$RUN/logs/blob$j.csv" "$RUN/logs/blob$j-resp.csv" > "$RUN/logs/blob$j.json" 2>> "$RUN/logs/blob$j.err" & echo $! > "$RUN/blob${j}pid" )
  done
  sleep 0.5; CPIDS="$(cat "$RUN/hotpid") $(cat "$RUN/blob0pid") $(cat "$RUN/blob1pid") $(cat "$RUN/blob2pid")"
else
  ( taskset -c $HOT_CPU $C hot $NP $ARM $I0 110 64 64 0 $((WMAX + 5)) "$STOPF" "$RUN/logs/hot.csv" "$RUN/logs/hot-resp.csv" > "$RUN/logs/hot.json" 2>> "$RUN/logs/hot.err" & echo $! > "$RUN/hotpid" )
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
    taskset -c $HOT_CPU $C clients $NP >> "$LOG" 2>&1
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
sleep 5
if kill -0 "$PID" 2>/dev/null; then jcmd $PID GC.class_histogram > "$RUN/hist/L1.txt" 2>&1; log "L1 done"; ALIVE=1; else log "node DEAD after W"; ALIVE=0; fi
sleep 3
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
  if [ "$ARM" = T ] && [ "$MODE" = R ] && [ ! -f "$BASE/KEPT_DUMP" ]; then
    mv "$f" "$RUN/" && echo "$RUN/$(basename "$f")" > "$BASE/KEPT_DUMP"; log "dump kept: $RUN/$(basename "$f")"
  else
    log "dump deleted (printed histogram in system.log): $(basename "$f") $(stat -c %s "$f")"; rm -f "$f"
  fi
done
rm -rf "$DUMP"
log "done alive=$ALIVE why=$WHY switch_at=$SWAT entry=$ENTRY"
echo "alive=$ALIVE why=$WHY switch_at=$SWAT" > "$RUN/DONE"
