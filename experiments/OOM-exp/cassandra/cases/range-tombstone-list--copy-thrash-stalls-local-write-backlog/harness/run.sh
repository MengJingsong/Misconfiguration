#!/bin/bash
# R17 stage-2 run driver (from U11's run.sh). usage: bash run.sh <label> <heap 8G|15872M|4G|2G|512M> <arm T|C|I|D> <mode R|S> [wmax]
#   mode R (main design): F to 0.45 x trigger (T/I/D batches of 1000 to pk=0; C batches of 100 over 1,000 partitions),
#          Q (10 s, L0, 20 s; arm I: setconcurrency MutationStage 1), W = hot stream 48/s (<= 96 out) + blob stream
#          12 x 4 MiB/s (<= 32 out), open loop; W stops at node death, wmax (450 s) or a r17.rt MemtableSwitchCount rise.
#   mode S (S512, U11's workload): F to 0.75 x trigger (batches of 100), W = hot closed loop 64 in flight, 150 s or a switch.
# Launch detached: ( setsid nohup bash run.sh ... < /dev/null > /dev/null 2>&1 & ); progress in <run>/logs/driver.log,
# done marker <run>/DONE. Node under systemd-run --user --scope -p MemorySwapMax=0, taskset 8 CPUs; data on /dev/shm.
set -u
LABEL=$1; HEAP=$2; ARM=$3; MODE=$4
BASE=/mydata/s4/r17; CASS=$BASE/cassandra; RUN=$BASE/$LABEL; SHM=/dev/shm/r17/$LABEL; H=$(dirname "$(readlink -f "$0")")
NODE_CPUS=24-31; HOT_CPU=20; BLOB_CPU=21; POLL_CPU=22
SP=7710; SSLP=7711; NP=9742; JMX=7799
if [ "$MODE" = R ]; then FRAC=0.45; WMAX=${5:-450}; else FRAC=0.75; WMAX=${5:-150}; fi
if [ "$MODE" = R ] && [ "$ARM" != C ]; then BATCH=1000; else BATCH=100; fi
rm -rf "$RUN" "$SHM"; mkdir -p "$RUN"/{logs,hist} "$SHM"/{data,commitlog,hints,saved_caches,cdc_raw}
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
log "start label=$LABEL heap=$HEAP arm=$ARM mode=$MODE frac=$FRAC batch=$BATCH wmax=$WMAX"
# pre-run checks: other Cassandra nodes, RAM, /dev/shm, ports
ps -eo pid,args | grep '[C]assandraDaemon' | cut -c1-250 >> "$LOG"
free -m >> "$LOG"; df -m /dev/shm >> "$LOG"
HMB=$(python3 -I -c "import sys; v=sys.argv[1]; print(int(v[:-1])*(1024 if v[-1]=='G' else 1))" "$HEAP")
AVAIL=$(free -m | awk '/^Mem:/{print $7}'); SHMF=$(df -m --output=avail /dev/shm | tail -1)
if [ "$AVAIL" -lt $((HMB + 35840)) ] || [ "$SHMF" -lt 40960 ]; then log "resources short avail=$AVAIL shm=$SHMF, abort"; echo resources > "$RUN/DONE"; exit 1; fi
for p in $SP $SSLP $NP $JMX; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && { log "port $p busy, abort"; echo busy > "$RUN/DONE"; exit 1; }; done
cp -a "$CASS/conf" "$RUN/conf"
Y=$RUN/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 'r17-$LABEL'|" \
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
export CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$RUN \
       JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true"
( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 taskset -c $NODE_CPUS "$CASS/bin/cassandra" -f \
    < /dev/null > "$RUN/logs/stdout.txt" 2>&1 & )
ok=0
for i in $(seq 1 90); do
  sleep 2
  if ss -ltn | awk '{print $4}' | grep -q ":$NP\$"; then ok=1; break; fi
done
PID=$(ps -eo pid,args | grep '[C]assandraDaemon' | grep -F -- "-Dcassandra.logdir=$RUN/logs " | awk '{print $1}' | head -1)
[ -z "$PID" ] && PID=$(ps -eo pid,args | grep '[C]assandraDaemon' | grep -F -- "$RUN/logs" | awk '{print $1}' | head -1)
echo "$PID" > "$RUN/pid.txt"
log "native up=$ok pid=$PID"
stopnode() {
  [ -n "${POLLPID:-}" ] && kill "$POLLPID" 2>/dev/null
  [ -n "${RSSPID:-}" ] && kill "$RSSPID" 2>/dev/null
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"; for i in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  fi
  log "node stopped"
}
if [ $ok -ne 1 ]; then log "node did not start"; stopnode; echo nostart > "$RUN/DONE"; rm -rf "$SHM"; exit 1; fi
tr '\0' ' ' < /proc/$PID/cmdline > "$RUN/logs/cmdline.txt"
grep -o -- '-XX:MaxDirectMemorySize=[^ ]*\|-Xmx[^ ]*\|-XX:ParallelGCThreads=[^ ]*\|-XX:ConcGCThreads=[^ ]*' "$RUN/logs/cmdline.txt" >> "$LOG"
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
echo "nproc_in_jvm=$(taskset -cp $PID 2>/dev/null)" >> "$LOG"
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
taskset -c $HOT_CPU $C fill $NP $ARM $TARGET "$RUN/logs/poll.log" $BATCH > "$RUN/logs/fill.json" 2>> "$LOG"
cat "$RUN/logs/fill.json" >> "$LOG"
I0=$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['I0'])" "$RUN/logs/fill.json" 2>/dev/null)
if [ -z "$I0" ]; then log "fill failed"; stopnode; echo fillfail > "$RUN/DONE"; rm -rf "$SHM"; exit 1; fi
log "quiesce"; sleep 10
jcmd $PID GC.class_histogram > "$RUN/hist/L0.txt" 2>&1; log "L0 done"
sleep 20
if [ "$ARM" = I ]; then
  "$CASS/bin/nodetool" -p $JMX setconcurrency MutationStage 1 >> "$LOG" 2>&1
  "$CASS/bin/nodetool" -p $JMX getconcurrency MutationStage >> "$LOG" 2>&1
fi
if [ "$ARM" = D ]; then
  ( k=0; while [ ! -f "$RUN/WDONE" ] && [ $k -lt 20 ]; do sleep 30; [ -f "$RUN/WDONE" ] && break; k=$((k+1));
      kill -0 $PID 2>/dev/null || break
      jcmd $PID GC.class_histogram > "$RUN/hist/D$(printf %02d $k)-$(date +%s).txt" 2>&1; done ) &
fi
SW0=$(tail -1 "$RUN/logs/poll.log" | awk -v h="$(head -1 "$RUN/logs/poll.log")" 'BEGIN{n=split(h,a," "); for(i=1;i<=n;i++) if(a[i]=="sw_rt") c=i} {print $c}')
log "W start I0=$I0 sw_rt0=$SW0"
WSTART=$(date +%s)
WHY=""
if [ "$MODE" = R ]; then
  STOPF=$RUN/STOPW
  ( taskset -c $HOT_CPU $C stream $NP hot $ARM $I0 48 96 $((WMAX + 5)) "$STOPF" "$RUN/logs/hot.csv" > "$RUN/logs/hot.json" 2>> "$RUN/logs/hot.err" & echo $! > "$RUN/hotpid" )
  ( taskset -c $BLOB_CPU $C stream $NP blob $ARM 0 12 32 $((WMAX + 5)) "$STOPF" "$RUN/logs/blob.csv" > "$RUN/logs/blob.json" 2>> "$RUN/logs/blob.err" & echo $! > "$RUN/blobpid" )
  sleep 0.5; HOTPID=$(cat "$RUN/hotpid"); BLOBPID=$(cat "$RUN/blobpid")
  while true; do
    sleep 1
    if ! kill -0 $PID 2>/dev/null; then WHY="node death"; break; fi
    if [ $(( $(date +%s) - WSTART )) -ge $WMAX ]; then WHY="wmax"; break; fi
    SW=$(tail -1 "$RUN/logs/poll.log" | awk -v h="$(head -1 "$RUN/logs/poll.log")" 'BEGIN{n=split(h,a," "); for(i=1;i<=n;i++) if(a[i]=="sw_rt") c=i} NF==n{print $c}')
    if [ -n "$SW" ] && [ "$SW" -gt "$SW0" ] 2>/dev/null; then WHY="rt switch ($SW0 -> $SW)"; break; fi
    if ! kill -0 $HOTPID 2>/dev/null && ! kill -0 $BLOBPID 2>/dev/null; then WHY="clients ended"; break; fi
  done
  log "W stop: $WHY after $(( $(date +%s) - WSTART )) s"
  touch "$STOPF"
  for i in $(seq 1 50); do kill -0 $HOTPID 2>/dev/null || kill -0 $BLOBPID 2>/dev/null || break; sleep 1; done
  kill $HOTPID $BLOBPID 2>/dev/null
  cat "$RUN/logs/hot.json" "$RUN/logs/blob.json" >> "$LOG"
else
  taskset -c $HOT_CPU $C closed $NP $ARM $I0 64 $WMAX "$RUN/logs/poll.log" "$RUN/logs/persec.csv" > "$RUN/logs/write.json" 2>> "$LOG"
  WHY=$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['stop'])" "$RUN/logs/write.json" 2>/dev/null)
  log "W stop: $WHY after $(( $(date +%s) - WSTART )) s"
  cat "$RUN/logs/write.json" >> "$LOG"
fi
touch "$RUN/WDONE"
sleep 5
if kill -0 "$PID" 2>/dev/null; then jcmd $PID GC.class_histogram > "$RUN/hist/L1.txt" 2>&1; log "L1 done"; ALIVE=1; else log "node DEAD after W"; ALIVE=0; fi
sleep 3
stopnode
grep -n 'java.lang.OutOfMemoryError' "$RUN/logs/system.log" "$RUN/logs/stdout.txt" > "$RUN/logs/oom-grep.txt" 2>/dev/null
grep -h 'Enqueuing flush of' "$RUN/logs/system.log" "$RUN/logs/debug.log" 2>/dev/null | sort -u > "$RUN/logs/flushes.txt"
ls -la "$RUN"/*.hprof >> "$LOG" 2>/dev/null
du -sh "$SHM" >> "$LOG" 2>/dev/null
rm -rf "$SHM"
for f in "$RUN"/*.hprof; do
  [ -f "$f" ] || continue
  ( setsid nohup nice -n 19 taskset -c 0-3 python3 -I "$H/hprofhist.py" "$f" 40 < /dev/null > "$RUN/hist/hprof-hist.txt" 2>&1 & )
done
log "done alive=$ALIVE why=$WHY"
echo "alive=$ALIVE why=$WHY" > "$RUN/DONE"
