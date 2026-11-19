#!/bin/bash
# U11 stage-2 run driver. usage: bash run.sh <label> <heap e.g. 2G|512M|8G> <arm T|C|I|D> [fill_frac=0.85] [w_count=20000] [w_maxsec=300]
# Launch detached: ( setsid nohup bash run.sh ... < /dev/null > /dev/null 2>&1 & ); progress in <run>/logs/driver.log, done marker <run>/DONE.
# One Cassandra node from /mydata/s4/u11-w4/cassandra under systemd-run --user --scope -p MemorySwapMax=0, taskset 8 cores.
set -u
LABEL=$1; HEAP=$2; ARM=$3; FRAC=${4:-0.85}; WCOUNT=${5:-20000}; WMAX=${6:-300}
BASE=/mydata/s4/u11-w4; CASS=$BASE/cassandra; RUN=$BASE/$LABEL; H=$(dirname "$(readlink -f "$0")")
NODE_CPUS=24-31; CLIENT_CPUS=22,23
SP=7610; SSLP=7611; NP=9642; JMX=7699
rm -rf "$RUN"; mkdir -p "$RUN"/{logs,data,commitlog,hints,saved_caches,cdc_raw,hist}
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
log "start label=$LABEL heap=$HEAP arm=$ARM frac=$FRAC wcount=$WCOUNT wmax=$WMAX"
cp -a "$CASS/conf" "$RUN/conf"
Y=$RUN/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 'u11-$LABEL'|" \
       -e "s|^storage_port:.*|storage_port: $SP|" -e "s|^ssl_storage_port:.*|ssl_storage_port: $SSLP|" \
       -e "s|^native_transport_port:.*|native_transport_port: $NP|" \
       -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"127.0.0.1:$SP\"|" \
       -e "s|^# hints_directory:.*|hints_directory: $RUN/hints|" \
       -e "s|^# commitlog_directory:.*|commitlog_directory: $RUN/commitlog|" \
       -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $RUN/cdc_raw|" \
       -e "s|^# saved_caches_directory:.*|saved_caches_directory: $RUN/saved_caches|" "$Y"
sed -i -e "s|^# data_file_directories:|data_file_directories:\n    - $RUN/data\n# (orig) data_file_directories:|" "$Y"
sed -i -e 's|^JMX_PORT="7199"|JMX_PORT="'$JMX'"|' "$RUN/conf/cassandra-env.sh"
echo "-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=$RUN/logs/gc.log:time,uptime,level,tags:filecount=50,filesize=20M" >> "$RUN/conf/jvm-server.options"
(cd "$CASS/conf" && diff -r . "$RUN/conf") > "$RUN/logs/conf.diff" 2>&1
for p in $SP $SSLP $NP $JMX; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && { log "port $p busy, abort"; echo busy > "$RUN/DONE"; exit 1; }; done
pgrep -af CassandraDaemon >> "$LOG" 2>&1
free -m >> "$LOG"
export CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$RUN \
       JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true"
( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 taskset -c $NODE_CPUS "$CASS/bin/cassandra" -f -p "$RUN/pid" \
    < /dev/null > "$RUN/logs/stdout.txt" 2>&1 & )
ok=0
for i in $(seq 1 120); do
  sleep 2
  if ss -ltn | awk '{print $4}' | grep -q ":$NP\$"; then ok=1; break; fi
done
PID=$(ps -eo pid,args | grep '[C]assandraDaemon' | grep -F -- "-Dcassandra.logdir=$RUN/logs " | awk '{print $1}' | head -1)
[ -z "$PID" ] && PID=$(ps -eo pid,args | grep '[C]assandraDaemon' | grep -F -- "$RUN/logs" | awk '{print $1}' | head -1)
echo "$PID" > "$RUN/pid.txt"
log "native up=$ok pid=$PID"
stopnode() {
  [ -n "${POLLPID:-}" ] && kill "$POLLPID" 2>/dev/null
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"; for i in $(seq 1 30); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  fi
  log "node stopped"
}
if [ $ok -ne 1 ]; then log "node did not start"; stopnode; echo nostart > "$RUN/DONE"; exit 1; fi
tr '\0' ' ' < /proc/$PID/cmdline > "$RUN/logs/cmdline.txt"
cd "$H"
( taskset -c $CLIENT_CPUS java -cp "$BASE/classes" Poll $JMX 1000 u11 rt > "$RUN/logs/poll.log" 2> "$RUN/logs/poll.err" & echo $! > "$RUN/pollpid" )
sleep 1; POLLPID=$(cat "$RUN/pollpid")
export CASSANDRA_HOME=$CASS
C="taskset -c $CLIENT_CPUS python3 -I $H/client.py"
$C schema $NP >> "$LOG" 2>&1
$C settings $NP > "$RUN/logs/settings.json" 2>> "$LOG"
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
$C fill $NP $ARM $TARGET "$RUN/logs/poll.log" > "$RUN/logs/fill.json" 2>> "$LOG"
cat "$RUN/logs/fill.json" >> "$LOG"
I0=$(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['I0'])" "$RUN/logs/fill.json" 2>/dev/null)
if [ -z "$I0" ]; then log "fill failed"; stopnode; echo fillfail > "$RUN/DONE"; exit 1; fi
log "quiesce"; sleep 10
jcmd $PID GC.class_histogram > "$RUN/hist/L0.txt" 2>&1; log "L0 done"
sleep 20
if [ "$ARM" = I ]; then
  "$CASS/bin/nodetool" -p $JMX setconcurrency MutationStage 1 >> "$LOG" 2>&1
  "$CASS/bin/nodetool" -p $JMX getconcurrency MutationStage >> "$LOG" 2>&1
fi
if [ "$ARM" = D ]; then
  ( k=0; while [ ! -f "$RUN/WDONE" ] && [ $k -lt 20 ]; do sleep 20; [ -f "$RUN/WDONE" ] && break; k=$((k+1));
      jcmd $PID GC.class_histogram > "$RUN/hist/D$(printf %02d $k)-$(date +%s).txt" 2>&1; done ) &
fi
log "W start I0=$I0"
$C write $NP $ARM $I0 $WCOUNT 64 $WMAX "$RUN/logs/poll.log" "$RUN/logs/persec.csv" > "$RUN/logs/write.json" 2>> "$LOG"
touch "$RUN/WDONE"
cat "$RUN/logs/write.json" >> "$LOG"
sleep 5
if kill -0 "$PID" 2>/dev/null; then jcmd $PID GC.class_histogram > "$RUN/hist/L1.txt" 2>&1; log "L1 done"; ALIVE=1; else log "node DEAD after W"; ALIVE=0; fi
sleep 3
stopnode
grep -n 'OutOfMemory' "$RUN/logs/system.log" "$RUN/logs/stdout.txt" > "$RUN/logs/oom-grep.txt" 2>/dev/null
ls -la "$RUN"/*.hprof >> "$LOG" 2>/dev/null
rm -rf "$RUN/data" "$RUN/commitlog" "$RUN/hints" "$RUN/cdc_raw" "$RUN/saved_caches"
log "done alive=$ALIVE"
echo "alive=$ALIVE" > "$RUN/DONE"
