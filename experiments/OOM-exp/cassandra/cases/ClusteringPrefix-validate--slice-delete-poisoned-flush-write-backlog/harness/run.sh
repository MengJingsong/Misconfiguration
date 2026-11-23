#!/bin/bash
# U15 stage-2 run driver (from R22's run.sh; design §2.5). usage: bash run.sh <label> <heap 2048M|4096M|8192M|15872M> <arm T|C|I|D1|PCAS> [wmax_s]
#   Phases: start node (unmodified build; arm I: patched build) -> schema -> settings read-back -> Q (10 s, L0 histogram, 10 s)
#   -> W: 4 data clients (127.0.0.2..5, 12/s each, <= 32 outstanding, 1 MiB values, ck = 0x01||seq) + poison client (127.0.0.1):
#        T, I: DELETE ... ck > 70,000 x 0x00, 1/s;  C: same with 65,000 B;  D1: the 70,000-B DELETE once;  PCAS: 70,000-B INSERT IF NOT EXISTS 1/s.
#   Stall check at W+30/60/90/150 s (2/4/8/15.5 GiB): applied delta over last 10 s, data issued over last 10 s, MutationStage active,
#   one jcmd Thread.print (threads in MemtableAllocator$SubAllocator.allocate).
#   Stop: node death, or wmax (T default 600 s at <= 4 GiB, 900 s above; other arms: the given W_C). If alive: L1 histogram, kill.
#   The dump (if any) is read by hprofhist.py in place (tmpfs); the first T dump at 2 GiB is kept on /mydata, every other dump deleted.
# Launch detached: ( setsid nohup bash run.sh ... < /dev/null > /dev/null 2>&1 & ); progress in <run>/logs/driver.log, marker <run>/DONE.
# Node under systemd-run --user --scope -p MemorySwapMax=0, taskset 24-31; data, commit log, hints, caches on /dev/shm/u15/<label>.
set -u
LABEL=$1; HEAP=$2; ARM=$3
BASE=/mydata/s4/u15; RUN=$BASE/$LABEL; SHM=/dev/shm/u15/$LABEL; DUMP=/dev/shm/u15/dump-$LABEL
if [ "$ARM" = I ]; then CASS=$BASE/cassandra-patched; else CASS=$BASE/cassandra; fi
H=$(dirname "$(readlink -f "$0")")
NODE_CPUS=24-31; DATA_CPUS=(12 13 14 15); POISON_CPU=16; POLL_CPU=17
SP=7720; SSLP=7721; NP=9752; JMX=7809
HMB=${HEAP%M}
case $HMB in 2048) SC=30;; 4096) SC=60;; 8192) SC=90;; *) SC=150;; esac
if [ $HMB -le 4096 ]; then WT=600; else WT=900; fi
WMAX=${4:-$WT}
case $ARM in
  T|I) PMODE=delete; PSIZE=70000; PRATE=1;;
  C)   PMODE=delete; PSIZE=65000; PRATE=1;;
  D1)  PMODE=once;   PSIZE=70000; PRATE=1;;
  PCAS) PMODE=cas;   PSIZE=70000; PRATE=1;;
  *) echo "bad arm"; exit 1;;
esac
rm -rf "$RUN" "$SHM" "$DUMP"; mkdir -p "$RUN"/{logs,hist} "$SHM"/{data,commitlog,hints,saved_caches,cdc_raw} "$DUMP"
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
col() { # value of column $1 in the last complete poll row
  tail -2 "$RUN/logs/poll.log" | awk -v h="$(head -1 "$RUN/logs/poll.log")" -v want="$1" 'BEGIN{n=split(h,a," "); for(i=1;i<=n;i++) if(a[i]==want) c=i} NF==n && $1 ~ /^[0-9]+$/ {v=$c} END{print v}'; }
log "start label=$LABEL heap=$HEAP arm=$ARM cass=$CASS poison=$PMODE/$PSIZE/$PRATE wmax=$WMAX stallcheck=W+$SC"
ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | cut -c1-250 >> "$LOG"
free -m >> "$LOG"; df -m /dev/shm >> "$LOG"
AVAIL=$(free -m | awk '/^Mem:/{print $7}'); SHMF=$(df -m --output=avail /dev/shm | tail -1)
if [ "$AVAIL" -lt $((HMB + 40960)) ] || [ "$SHMF" -lt 40960 ]; then log "resources short avail=$AVAIL shm=$SHMF, abort"; echo resources > "$RUN/DONE"; exit 1; fi
if ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | grep -q .; then log "another CassandraDaemon runs, abort"; echo othernode > "$RUN/DONE"; exit 1; fi
for p in $SP $SSLP $NP $JMX; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && { log "port $p busy, abort"; echo busy > "$RUN/DONE"; exit 1; }; done
cp -a "$CASS/conf" "$RUN/conf"
Y=$RUN/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 'u15-$LABEL'|" \
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
unzip -l "$(ls $CASS/build/apache-cassandra-*.jar | grep -v -e javadoc -e sources | head -1)" 'org/apache/cassandra/cql3/statements/ModificationStatement.class' >> "$LOG" 2>&1
export CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=$HEAP CASSANDRA_HEAPDUMP_DIR=$DUMP
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
grep -o -- '-XX:MaxDirectMemorySize=[^ ]*\|-Xmx[^ ]*\|-Xms[^ ]*\|-XX:OnOutOfMemoryError=[^ ]*\|-XX:HeapDumpPath=[^ ]*\|-ea \|-XX:G1HeapRegionSize=[^ ]*' "$RUN/logs/cmdline.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
jcmd $PID VM.flags > "$RUN/logs/vmflags.txt" 2>&1
grep -o 'ParallelGCThreads=[0-9]*\|ConcGCThreads=[0-9]*\|MaxDirectMemorySize=[0-9]*\|G1HeapRegionSize=[0-9]*\|MaxHeapSize=[0-9]*' "$RUN/logs/vmflags.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
echo "jvm_cpus=$(taskset -cp $PID 2>/dev/null)" >> "$LOG"
( while kill -0 $PID 2>/dev/null; do echo "$(date +%s) $(awk '/RssAnon/{print $2}' /proc/$PID/status 2>/dev/null)"; sleep 1; done > "$RUN/logs/rss.log" 2>/dev/null & echo $! > "$RUN/rsspid" )
RSSPID=$(cat "$RUN/rsspid")
cd "$H"
( taskset -c $POLL_CPU java -cp "$BASE/classes" Poll $JMX 1000 > "$RUN/logs/poll.log" 2> "$RUN/logs/poll.err" & echo $! > "$RUN/pollpid" )
sleep 1; POLLPID=$(cat "$RUN/pollpid")
export CASSANDRA_HOME=$BASE/cassandra
C="python3 -I $H/client.py"
taskset -c $POISON_CPU $C schema $NP >> "$LOG" 2>&1
taskset -c $POISON_CPU $C settings $NP > "$RUN/logs/settings.json" 2>> "$LOG"
cat "$RUN/logs/settings.json" >> "$LOG"
log "quiesce"; sleep 10
timeout 120 jcmd $PID GC.class_histogram > "$RUN/hist/L0.txt" 2>&1; log "L0 done"
sleep 10
log "W start sw0=$(col sw) applied0=$(col applied)"
WSTART=$(date +%s)
WHY=""; STALL=""
STOPF=$RUN/STOPW
for j in 0 1 2 3; do
  ( taskset -c ${DATA_CPUS[$j]} $C data $NP 127.0.0.$((j + 2)) $((j + 2)) 12 32 $((WMAX + 5)) "$STOPF" "$RUN/logs/data$j.csv" "$RUN/logs/data$j-resp.csv" > "$RUN/logs/data$j.json" 2>> "$RUN/logs/data$j.err" & echo $! > "$RUN/data${j}pid" )
done
( taskset -c $POISON_CPU $C poison $NP 127.0.0.1 $PMODE $PSIZE $PRATE 4 $((WMAX + 5)) "$STOPF" "$RUN/logs/poison.csv" "$RUN/logs/poison-resp.csv" > "$RUN/logs/poison.json" 2>> "$RUN/logs/poison.err" & echo $! > "$RUN/poisonpid" )
sleep 0.5; CPIDS="$(cat "$RUN/data0pid") $(cat "$RUN/data1pid") $(cat "$RUN/data2pid") $(cat "$RUN/data3pid") $(cat "$RUN/poisonpid")"
log "clients $CPIDS"
issued_sum() { local s=0; for j in 0 1 2 3; do v=$(tail -1 "$RUN/logs/data$j.csv" 2>/dev/null | cut -d, -f2); [[ "$v" =~ ^[0-9]+$ ]] && s=$((s + v)); done; echo $s; }
A10=""; I10=""
while true; do
  sleep 1
  EL=$(( $(date +%s) - WSTART ))
  if ! kill -0 $PID 2>/dev/null; then WHY="node death"; break; fi
  if [ $EL -ge $WMAX ]; then WHY="wmax"; break; fi
  if [ $EL -ge $((SC - 10)) ] && [ -z "$A10" ]; then A10=$(col applied); I10=$(issued_sum); fi
  if [ -z "$STALL" ] && [ $EL -ge $SC ] && [ -n "$A10" ]; then
    A=$(col applied); I=$(issued_sum); ACT=$(col active)
    timeout 90 jcmd $PID Thread.print > "$RUN/logs/stallcheck-threads.txt" 2>&1
    NPARK=$(python3 -I - "$RUN/logs/stallcheck-threads.txt" <<'EOF'
import sys, re
t = open(sys.argv[1], errors='replace').read().split('\n\n')
park = [b for b in t if 'MemtableAllocator$SubAllocator.allocate' in b]
names = [re.match(r'"([^"]+)"', b.strip()).group(1) for b in park if re.match(r'"([^"]+)"', b.strip())]
kinds = {}
for n in names:
    k = re.sub(r'[-:]?\d+$', '', n); kinds[k] = kinds.get(k, 0) + 1
print('%d %s' % (len(park), ';'.join('%s=%d' % kv for kv in sorted(kinds.items()))))
EOF
)
    DA=$((A - A10)); DI=$((I - I10))
    if [ $DA -lt 5 ] && [ $DI -ge 300 ] && [ "$ACT" = 32 ]; then ST=yes; else ST=no; fi
    STALL="stalled=$ST applied_delta10=$DA issued_delta10=$DI mutation_active=$ACT parked_in_allocate=$NPARK"
    log "stall check W+$EL: $STALL"
    taskset -c $POISON_CPU timeout 20 $C clients $NP >> "$LOG" 2>&1
  fi
  PM=$(stat -c %Y "$RUN/logs/poll.log" 2>/dev/null || echo 0); GM=$(stat -c %Y "$RUN/logs/gc.log" 2>/dev/null || echo 0); NOW=$(date +%s)
  if [ $((NOW - PM)) -ge 180 ] && [ $((NOW - GM)) -ge 180 ]; then
    timeout 90 jcmd $PID Thread.print > "$RUN/logs/hung-threads.txt" 2>&1; kill -9 $PID; WHY="hung"; break
  fi
done
log "W stop: $WHY after $(( $(date +%s) - WSTART )) s"
touch "$STOPF"
for i in $(seq 1 50); do alive=0; for c in $CPIDS; do kill -0 $c 2>/dev/null && alive=1; done; [ $alive -eq 0 ] && break; sleep 1; done
for c in $CPIDS; do kill $c 2>/dev/null; done
for f in data0 data1 data2 data3 poison; do [ -f "$RUN/logs/$f.json" ] && cat "$RUN/logs/$f.json" >> "$LOG"; done
sleep 3
if kill -0 "$PID" 2>/dev/null; then timeout 120 jcmd $PID GC.class_histogram > "$RUN/hist/L1.txt" 2>&1; log "L1 done"; ALIVE=1; else log "node DEAD after W"; ALIVE=0; fi
stopnode
# wait for a heap dump still being written by a dying JVM (kill -9 runs after the dump)
for i in $(seq 1 300); do ps -eo pid,comm,args | awk '$2=="java"' | grep -qF -- "cassandra.logdir=$RUN/logs" || break; sleep 1; done
grep -nF 'java.lang.OutOfMemoryError' "$RUN/logs/system.log" "$RUN/logs/stdout.txt" 2>/dev/null | grep -v 'JVM Arguments' > "$RUN/logs/oom-grep.txt"
grep -h 'Enqueuing flush of\|Flushing largest\|Completed flushing\|exceeded maximum of 65535\|Writing Memtable' "$RUN/logs/system.log" "$RUN/logs/debug.log" 2>/dev/null | sort -u > "$RUN/logs/flushes.txt"
ls -la "$DUMP" >> "$LOG" 2>/dev/null
du -sh "$SHM"/* >> "$LOG" 2>/dev/null
rm -rf "$SHM"
for f in "$DUMP"/*.hprof; do
  [ -f "$f" ] || continue
  log "dump $(basename "$f") $(stat -c %s "$f") B: hprofhist"
  nice -n 19 taskset -c 0-3 python3 -I "$H/hprofhist.py" "$f" 30 > "$RUN/hist/dump-hist.txt" 2>&1
  log "hprofhist done"
  if [ "$ARM" = T ] && [ "$HMB" = 2048 ] && [ ! -f "$BASE/KEPT_DUMP" ]; then
    mv "$f" "$RUN/" && echo "$RUN/$(basename "$f")" > "$BASE/KEPT_DUMP"; log "dump kept: $RUN/$(basename "$f")"
  else
    log "dump deleted after hprofhist: $(basename "$f")"; rm -f "$f"
  fi
done
rm -rf "$DUMP"
log "done alive=$ALIVE why=$WHY stall=$STALL"
echo "alive=$ALIVE why=$WHY $STALL" > "$RUN/DONE"
