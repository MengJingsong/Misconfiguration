#!/bin/bash
# U13 stage-2 run driver (design §2.5-§2.7). usage: bash run.sh <label> <heap e.g. 4G|15872M> <direct e.g. 512M> <arm M|CTL|INT> [maxload_s=720]
# Launch detached: ( setsid nohup bash run.sh ... < /dev/null > /dev/null 2>&1 & ); progress in <run>/logs/driver.log,
# done marker <run>/DONE. Node: bin/cassandra -f under systemd-run --user --scope -p MemorySwapMax=0; data under /mydata/s4/u13/<label>.
# Stop: OOM in system.log/stdout or node death (endpoint), 6 completed u13.t flushes whose enqueue usage was >= 0.9 x the
# predicted 1/3 of the on-heap limit (>= 30 %), or <maxload_s> of load (12 min), whichever first. Hung rule: no JMX sample
# and no GC-log write for 180 s -> thread dump, kill -9.
set -u
LABEL=$1; HEAP=$2; DIRECT=$3; ARM=$4; MAXLOAD=${5:-720}
BASE=/mydata/s4/u13; CASS=/mydata/s4/cassandra-base; RUN=$BASE/$LABEL; DUMP=$BASE/dump-$LABEL; CLS=$BASE/classes
H=$(dirname "$(readlink -f "$0")")
NP=9042; JMX=7199
rm -rf "$RUN" "$DUMP"; mkdir -p "$RUN"/{logs,nmt,data,commitlog,hints,saved_caches,cdc_raw} "$DUMP"
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
log "start label=$LABEL heap=$HEAP direct=$DIRECT arm=$ARM maxload=$MAXLOAD"
free -m >> "$LOG"; df -m /mydata >> "$LOG"
if ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | grep -q .; then log "another CassandraDaemon runs, abort"; echo othernode > "$RUN/DONE"; exit 1; fi
for p in 7000 $NP $JMX; do ss -ltn | awk '{print $4}' | grep -q ":$p\$" && { log "port $p busy, abort"; echo busy > "$RUN/DONE"; exit 1; }; done
FREE=$(df -m --output=avail /mydata | tail -1); if [ "$FREE" -lt 15360 ]; then log "disk short $FREE MiB, abort"; echo disk > "$RUN/DONE"; exit 1; fi
cp -a "$CASS/conf" "$RUN/conf"
Y=$RUN/conf/cassandra.yaml
sed -i -e "s|^# hints_directory:.*|hints_directory: $RUN/hints|" \
       -e "s|^# commitlog_directory:.*|commitlog_directory: $RUN/commitlog|" \
       -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $RUN/cdc_raw|" \
       -e "s|^# saved_caches_directory:.*|saved_caches_directory: $RUN/saved_caches|" "$Y"
sed -i -e "s|^# data_file_directories:|data_file_directories:\n    - $RUN/data\n# (orig) data_file_directories:|" "$Y"
echo "-XX:NativeMemoryTracking=summary" >> "$RUN/conf/jvm-server.options"
(cd "$CASS/conf" && diff -r . "$RUN/conf") > "$RUN/logs/conf.diff" 2>&1
export CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT CASSANDRA_HEAPDUMP_DIR=$DUMP \
       JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true"
( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 "$CASS/bin/cassandra" -f < /dev/null > "$RUN/logs/stdout.txt" 2>&1 & )
ok=0
for i in $(seq 1 120); do
  sleep 2
  if ss -ltn | awk '{print $4}' | grep -q ":$NP\$"; then ok=1; break; fi
done
PID=$(ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | grep -F -- "-Dcassandra.logdir=$RUN/logs " | awk '{print $1}' | head -1)
[ -z "$PID" ] && PID=$(ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | grep -F -- "$RUN/logs" | awk '{print $1}' | head -1)
echo "$PID" > "$RUN/pid.txt"
log "native up=$ok pid=$PID"
stopall() {
  [ -n "${POLLPID:-}" ] && kill "$POLLPID" 2>/dev/null
  [ -n "${NMTPID:-}" ] && kill "$NMTPID" 2>/dev/null
  [ -n "${TOPPID:-}" ] && kill "$TOPPID" 2>/dev/null
  [ -n "${LPID:-}" ] && kill "$LPID" 2>/dev/null
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"; for i in $(seq 1 40); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  fi
  log "node stopped"
}
if [ $ok -ne 1 ]; then log "node did not start"; stopall; echo nostart > "$RUN/DONE"; exit 1; fi
tr '\0' ' ' < /proc/$PID/cmdline > "$RUN/logs/cmdline.txt"
grep -o -- '-XX:MaxDirectMemorySize=[^ ]*\|-Xmx[^ ]*\|-Xms[^ ]*\|-XX:HeapDumpPath=[^ ]*\|-XX:NativeMemoryTracking=[^ ]*' "$RUN/logs/cmdline.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
jcmd $PID VM.flags > "$RUN/logs/vmflags.txt" 2>&1
grep -o 'MaxDirectMemorySize=[0-9]*\|MaxHeapSize=[0-9]*\|ParallelGCThreads=[0-9]*\|ConcGCThreads=[0-9]*' "$RUN/logs/vmflags.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
( java -cp "$CLS" Poll $JMX 200 > "$RUN/logs/poll.log" 2> "$RUN/logs/poll.err" & echo $! > "$RUN/pollpid" )
( while kill -0 $PID 2>/dev/null; do echo "@@ $(date +%s.%N | cut -c1-14)"; jcmd $PID VM.native_memory summary 2>&1 | grep -E 'Total:|^-  *(Java Heap|Other|Internal|Thread|GC|Class|Code)' ; sleep 5; done > "$RUN/nmt/nmt.log" 2>/dev/null & echo $! > "$RUN/nmtpid" )
( while kill -0 $PID 2>/dev/null; do echo "@@ $(date +%s)"; top -b -n1 -w 200 | sed -n 7,14p; sleep 10; done > "$RUN/logs/top.log" 2>/dev/null & echo $! > "$RUN/toppid" )
sleep 1; POLLPID=$(cat "$RUN/pollpid"); NMTPID=$(cat "$RUN/nmtpid"); TOPPID=$(cat "$RUN/toppid")
JCP="$CLS:$CASS/lib/*"
JOPT="-Xmx1G -Dlogback.configurationFile=$CASS/conf/logback-tools.xml"
java $JOPT -cp "$JCP" Load schema $ARM $NP >> "$LOG" 2>> "$RUN/logs/load.err"
sleep 3
STOPF=$RUN/STOPLOAD
( java $JOPT -cp "$JCP" Load load $ARM $NP 64 10 $MAXLOAD "$STOPF" "$RUN/logs/load.csv" > "$RUN/logs/load.json" 2>> "$RUN/logs/load.err" & echo $! > "$RUN/lpid" )
sleep 0.5; LPID=$(cat "$RUN/lpid")
log "load started pid=$LPID"
LSTART=$(date +%s); WHY=""; OOMAT=""
nflush() { python3 -I "$H/flushes.py" "$RUN/logs/system.log" count 2>/dev/null || echo 0; }
while true; do
  sleep 1
  EL=$(( $(date +%s) - LSTART ))
  if grep -qF 'java.lang.OutOfMemoryError' "$RUN/logs/system.log" "$RUN/logs/stdout.txt" 2>/dev/null; then WHY="OOM"; OOMAT=$EL; break; fi
  if ! kill -0 $PID 2>/dev/null; then WHY="node death"; break; fi
  if [ $EL -ge $((MAXLOAD + 60)) ]; then WHY="maxload"; break; fi
  if ! kill -0 $LPID 2>/dev/null; then WHY="load ended"; break; fi
  if [ $((EL % 5)) -eq 0 ]; then
    N=$(nflush); if [ "${N:-0}" -ge 6 ]; then WHY="6 flushes"; break; fi
  fi
  PM=$(stat -c %Y "$RUN/logs/poll.log" 2>/dev/null || echo 0); GM=$(stat -c %Y "$RUN/logs/gc.log" 2>/dev/null || echo 0); NOW=$(date +%s)
  if [ $((NOW - PM)) -ge 180 ] && [ $((NOW - GM)) -ge 180 ]; then
    jcmd $PID Thread.print > "$RUN/logs/hung-threads.txt" 2>&1; kill -9 $PID; WHY="hung"; break
  fi
done
log "load stop: $WHY after $EL s (oom_at=$OOMAT)"
touch "$STOPF"
if [ "$WHY" = OOM ]; then
  # let the JVM finish the heap dump / histogram (forced heap OOM after a direct OOM), then stop it
  for i in $(seq 1 180); do
    kill -0 $PID 2>/dev/null || break
    if grep -q 'Heap dump file created' "$RUN/logs/stdout.txt" 2>/dev/null && [ $i -ge 20 ]; then break; fi
    sleep 1
  done
  log "after OOM wait: alive=$(kill -0 $PID 2>/dev/null && echo 1 || echo 0)"
  kill -0 $PID 2>/dev/null && jcmd $PID Thread.print > "$RUN/logs/threads-after-oom.txt" 2>&1
fi
for i in $(seq 1 75); do kill -0 $LPID 2>/dev/null || break; sleep 1; done
cat "$RUN/logs/load.json" >> "$LOG" 2>/dev/null
sleep 2
stopall
for i in $(seq 1 120); do ps -eo pid,comm,args | awk '$2=="java"' | grep -qF -- "cassandra.logdir=$RUN/logs" || break; sleep 1; done
grep -nF 'java.lang.OutOfMemoryError' "$RUN/logs/system.log" "$RUN/logs/stdout.txt" 2>/dev/null | grep -v 'JVM Arguments' > "$RUN/logs/oom-grep.txt"
python3 -I "$H/flushes.py" "$RUN/logs/system.log" table > "$RUN/logs/flushes.txt" 2>&1
du -sh "$RUN/data" "$RUN/commitlog" >> "$LOG" 2>/dev/null
rm -rf "$RUN/data" "$RUN/commitlog" "$RUN/hints" "$RUN/saved_caches" "$RUN/cdc_raw"
for f in "$DUMP"/*.hprof; do
  [ -f "$f" ] || continue
  if [ "$ARM" = M ] && [ ! -f "$BASE/KEPT_DUMP" ]; then
    mv "$f" "$RUN/" && echo "$RUN/$(basename "$f")" > "$BASE/KEPT_DUMP"; log "dump kept: $RUN/$(basename "$f") $(stat -c %s "$RUN/$(basename "$f")")"
  else
    log "dump deleted (histogram printed in system.log): $(basename "$f") $(stat -c %s "$f")"; rm -f "$f"
  fi
done
rm -rf "$DUMP"
log "done why=$WHY oom_at=$OOMAT"
echo "why=$WHY oom_at=$OOMAT" > "$RUN/DONE"
