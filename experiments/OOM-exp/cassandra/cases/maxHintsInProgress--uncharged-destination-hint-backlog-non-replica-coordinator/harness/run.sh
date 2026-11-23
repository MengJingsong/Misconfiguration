#!/bin/bash
# B23 stage-2 run driver (design §2.3, §2.5, §2.7). usage: bash run.sh <label> <n1-heap e.g. 2G> <arm T|C|I> <N> [size=64000] [threads=200] [extra-stress=0]
#   Three fresh instances on loopback: n1 127.0.0.31 (victim coordinator, JMX 7231, token 0, data/commitlog/hints on /mydata),
#   n2 127.0.0.32 (seed, live replica, JMX 7232, token -2, 8G heap, data on /dev/shm/b23/<label>),
#   n3 127.0.0.33 (replica stopped before the load, JMX 7233, token -1, 8G heap, data on /dev/shm). num_tokens 1, RF 2.
#   Arm T: original build, n3 stopped; C: original, n3 up; I: n1 runs /mydata/s4/b23/cassandra-fix (LoadingCache), n3 stopped.
#   Label starting with K1: also one jstack at K >= 5120 and one GC.class_histogram at K >= 8000 (calibration only).
# Stop (first of): n1 death; stress done + 60 s; 600 s from load start; /dev/shm used > 56 GiB; n2 death (invalid); hung (no poll/GC 180 s).
# Launch detached: ( setsid nohup bash run.sh ... < /dev/null > /dev/null 2>&1 & ); progress <run>/logs/driver.log; done marker <run>/DONE.
set -u
LABEL=$1; HEAP=$2; ARM=$3; N=$4; SIZE=${5:-64000}; THREADS=${6:-200}; EXTRA=${7:-0}
BASE=/mydata/s4/b23; ORIG=/mydata/s4/cassandra-base; FIX=$BASE/cassandra-fix
RUN=$BASE/$LABEL; SHM=/dev/shm/b23/$LABEL; DUMP=$RUN/dump
H=$BASE/harness
if [ "$ARM" = I ]; then H1=$FIX; else H1=$ORIG; fi
rm -rf "$RUN" "$SHM"; mkdir -p "$RUN/logs" "$RUN/hist" "$DUMP" "$SHM"
LOG=$RUN/logs/driver.log
log() { echo "$(date +%s.%N | cut -c1-14) $(TZ=America/New_York date +%T) $*" >> "$LOG"; }
col() { tail -2 "$RUN/logs/poll1.log" 2>/dev/null | awk -v h="$(head -1 "$RUN/logs/poll1.log" 2>/dev/null)" -v want="$1" 'BEGIN{n=split(h,a," "); for(i=1;i<=n;i++) if(a[i]==want) c=i} NF==n && $1 ~ /^[0-9]+$/ {v=$c} END{print v}'; }
log "start label=$LABEL n1heap=$HEAP arm=$ARM N=$N size=$SIZE threads=$THREADS extra=$EXTRA n1home=$H1"
hm=$(TZ=America/New_York date +%H%M); if [ "$hm" -ge 1315 ]; then log "past 13:15 New York, not starting"; echo late > "$RUN/DONE"; exit 1; fi
if ps -eo comm,args | awk '$1=="java" && /CassandraDaemon/' | grep -q .; then log "another CassandraDaemon runs, abort"; echo othernode > "$RUN/DONE"; exit 1; fi
free -m >> "$LOG"; df -m /dev/shm /mydata >> "$LOG"
ADDR=(x 127.0.0.31 127.0.0.32 127.0.0.33); TOK=(x 0 -2 -1); JMX=(x 7231 7232 7233)
declare -A PID
for i in 1 2 3; do
  if [ $i = 1 ]; then HOME_I=$H1; D=$RUN/n1; else HOME_I=$ORIG; D=$SHM/n$i; fi
  mkdir -p "$RUN/n$i/logs" "$D"/{data,commitlog,hints,saved_caches,cdc_raw}
  cp -a "$HOME_I/conf" "$RUN/n$i/conf"; Y=$RUN/n$i/conf/cassandra.yaml
  sed -i -e "s|^cluster_name:.*|cluster_name: 'b23-$LABEL'|" -e "s|^num_tokens:.*|num_tokens: 1|" \
         -e "s|^# initial_token:.*|initial_token: ${TOK[$i]}|" \
         -e "s|^listen_address:.*|listen_address: ${ADDR[$i]}|" -e "s|^rpc_address:.*|rpc_address: ${ADDR[$i]}|" \
         -e "s|- seeds: \"127.0.0.1:7000\"|- seeds: \"127.0.0.32:7000\"|" \
         -e "s|^# hints_directory:.*|hints_directory: $D/hints|" \
         -e "s|^# commitlog_directory:.*|commitlog_directory: $D/commitlog|" \
         -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: $D/cdc_raw|" \
         -e "s|^# saved_caches_directory:.*|saved_caches_directory: $D/saved_caches|" "$Y"
  sed -i -e "s|^# data_file_directories:|data_file_directories:\n    - $D/data\n# (orig) data_file_directories:|" "$Y"
  sed -i -e 's|^JMX_PORT="7199"|JMX_PORT="'${JMX[$i]}'"|' "$RUN/n$i/conf/cassandra-env.sh"
  echo "-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=$RUN/n$i/logs/gc.log:time,uptime,level,tags:filecount=50,filesize=20M" >> "$RUN/n$i/conf/jvm-server.options"
  (cd "$HOME_I/conf" && diff -r . "$RUN/n$i/conf") > "$RUN/n$i/logs/conf.diff" 2>&1
done
startnode() { # $1 = node index
  local i=$1 HOME_I=$ORIG HP=8G HD=$SHM/dump-n$1
  if [ $i = 1 ]; then HOME_I=$H1; HP=$HEAP; HD=$DUMP; fi
  mkdir -p "$HD"
  ( export CASSANDRA_CONF=$RUN/n$i/conf CASSANDRA_LOG_DIR=$RUN/n$i/logs MAX_HEAP_SIZE=$HP CASSANDRA_HEAPDUMP_DIR=$HD \
      JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true"
    ulimit -n 1048576 2>/dev/null
    setsid nohup systemd-run --user --scope -p MemorySwapMax=0 "$HOME_I/bin/cassandra" -f < /dev/null > "$RUN/n$i/logs/stdout.txt" 2>&1 & )
  local ok=0
  for k in $(seq 1 120); do sleep 2
    if ss -ltn | awk '{print $4}' | grep -qF "${ADDR[$i]}:9042"; then ok=1; break; fi
    ps -eo comm,args | awk '$1=="java"' | grep -qF -- "-Dcassandra.logdir=$RUN/n$i/logs" || [ $k -lt 5 ] || break
  done
  PID[$i]=$(ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/' | grep -F -- "-Dcassandra.logdir=$RUN/n$i/logs" | awk '{print $1}' | head -1)
  log "n$i native up=$ok pid=${PID[$i]}"; echo "${PID[$i]}" > "$RUN/n$i/pid.txt"
  [ $ok = 1 ]
}
stopall() {
  for p in ${BGP:-}; do kill "$p" 2>/dev/null; done
  for i in 1 2 3; do
    p=${PID[$i]:-}; [ -z "$p" ] && continue
    if kill -0 "$p" 2>/dev/null; then kill "$p"; for k in $(seq 1 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -0 "$p" 2>/dev/null && kill -9 "$p"; fi
  done
  log "all nodes stopped"
}
fail() { log "FAIL: $*"; stopall; echo "fail: $*" > "$RUN/DONE"; rm -rf "$SHM"; rm -rf "$RUN"/n1/{data,commitlog,hints,saved_caches,cdc_raw}; exit 1; }
startnode 2 || fail "n2 start"
startnode 3 || fail "n3 start"
startnode 1 || fail "n1 start"
NT1="$ORIG/bin/nodetool -h 127.0.0.1 -p 7231"
$NT1 status > "$RUN/logs/status-up.txt" 2>&1; cat "$RUN/logs/status-up.txt" >> "$LOG"
[ "$(grep -c '^UN' "$RUN/logs/status-up.txt")" = 3 ] || fail "not 3 UN"
P1=${PID[1]}
tr '\0' ' ' < /proc/$P1/cmdline > "$RUN/logs/n1-cmdline.txt"
grep -o -- '-XX:MaxDirectMemorySize=[^ ]*\|-Xmx[^ ]*\|-Xms[^ ]*\|-XX:HeapDumpPath=[^ ]*\|-XX:+Use[A-Za-z0-9]*GC' "$RUN/logs/n1-cmdline.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
jcmd $P1 VM.flags > "$RUN/logs/n1-vmflags.txt" 2>&1
grep -o 'MaxDirectMemorySize=[0-9]*\|MaxHeapSize=[0-9]*\|G1HeapRegionSize=[0-9]*\|ParallelGCThreads=[0-9]*' "$RUN/logs/n1-vmflags.txt" | tr '\n' ' ' >> "$LOG"; echo >> "$LOG"
cat /proc/$P1/cgroup >> "$LOG"
STRESS="$ORIG/tools/bin/cassandra-stress"
SOPT="cl=ONE -schema replication(strategy=SimpleStrategy,factor=2) -col size=FIXED($SIZE) n=FIXED(1) -mode native cql3 protocolVersion=4 -node whitelist 127.0.0.31"
log "schema: stress write n=1000"
$STRESS write n=1000 $SOPT -rate threads=50 -errors ignore retries=0 > "$RUN/logs/stress-schema.txt" 2>&1
tail -25 "$RUN/logs/stress-schema.txt" | grep -i "op rate\|total partitions\|total errors\|error" >> "$LOG"
if [ "$ARM" != C ]; then
  log "stopping n3 (nodetool stopdaemon)"
  "$ORIG/bin/nodetool" -h 127.0.0.1 -p 7233 stopdaemon >> "$LOG" 2>&1
  for k in $(seq 1 30); do kill -0 ${PID[3]} 2>/dev/null || break; sleep 1; done
  kill -0 ${PID[3]} 2>/dev/null && { log "n3 still alive, SIGTERM"; kill ${PID[3]}; sleep 10; kill -9 ${PID[3]} 2>/dev/null; }
  for k in $(seq 1 30); do $NT1 status 2>/dev/null | grep -q '^DN *127.0.0.33' && break; sleep 1; done
  $NT1 status > "$RUN/logs/status-down.txt" 2>&1; cat "$RUN/logs/status-down.txt" >> "$LOG"
  grep -q '^DN *127.0.0.33' "$RUN/logs/status-down.txt" || fail "n3 not DN at n1"
fi
log "n1 hints dir before load: $(du -sb $RUN/n1/hints | cut -f1) B, files $(ls $RUN/n1/hints | wc -l)"
cd "$H"
( java -cp "$BASE/classes" Poll 7231 1000 > "$RUN/logs/poll1.log" 2> "$RUN/logs/poll1.err" & echo $! > "$RUN/pp1" )
( java -cp "$BASE/classes" Poll 7232 1000 > "$RUN/logs/poll2.log" 2> "$RUN/logs/poll2.err" & echo $! > "$RUN/pp2" )
( while kill -0 $P1 2>/dev/null; do echo "$(date +%s.%N | cut -c1-14) $(du -sb $RUN/n1/hints 2>/dev/null | cut -f1) $(awk '/RssAnon/{print $2}' /proc/$P1/status 2>/dev/null)"; sleep 1; done > "$RUN/logs/hints-rss.log" 2>/dev/null & echo $! > "$RUN/pp3" )
( while true; do echo "$(date +%s) $(df -m --output=used /dev/shm | tail -1)"; sleep 5; done > "$RUN/logs/shm.log" & echo $! > "$RUN/pp4" )
sleep 3
BGP="$(cat $RUN/pp1) $(cat $RUN/pp2) $(cat $RUN/pp3) $(cat $RUN/pp4)"
log "MaxHintsInProgress: $(grep MaxHintsInProgress $RUN/logs/poll1.err)"
LSTART=$(date +%s); log "load start N=$N"
( $STRESS write n=$N $SOPT -rate threads=$THREADS -errors ignore retries=0 -log interval=1 file=$RUN/logs/stress-main.log > "$RUN/logs/stress-stdout.txt" 2>&1 & echo $! > "$RUN/spid" )
sleep 0.5; SPIDS=$(cat "$RUN/spid")
if [ "$EXTRA" -ge 1 ]; then
  ( $STRESS write n=$N $SOPT -rate threads=$THREADS -errors ignore retries=0 -pop seq=$((N+1))..$((2*N)) -log interval=1 file=$RUN/logs/stress-extra.log > "$RUN/logs/stress-extra-stdout.txt" 2>&1 & echo $! > "$RUN/spid2" )
  sleep 0.5; SPIDS="$SPIDS $(cat "$RUN/spid2")"
fi
log "stress pids $SPIDS"
WHY=""; SDONE=""; J1=""; H8=""; VALID=1
while true; do
  sleep 1; NOW=$(date +%s); EL=$((NOW - LSTART))
  if ! kill -0 $P1 2>/dev/null; then WHY="n1 death at L+$EL"; break; fi
  if ! kill -0 ${PID[2]} 2>/dev/null; then WHY="n2 death at L+$EL"; VALID=0; break; fi
  if [ $EL -ge 600 ]; then WHY="600 s cap"; break; fi
  SU=$(tail -1 "$RUN/logs/shm.log" | awk '{print $2}'); if [ -n "$SU" ] && [ "$SU" -gt 57344 ]; then WHY="tmpfs > 56 GiB at L+$EL"; VALID=0; break; fi
  K=$(col K)
  case "$LABEL" in K1*)
    if [ -z "$J1" ] && [ -n "$K" ] && [ "$K" -ge 5120 ] 2>/dev/null; then J1=$EL; jstack $P1 > "$RUN/logs/jstack-K5120.txt" 2>&1; log "jstack at L+$EL K=$K"; fi
    if [ -z "$H8" ] && [ -n "$K" ] && [ "$K" -ge 8000 ] 2>/dev/null; then H8=$EL; jcmd $P1 GC.class_histogram > "$RUN/hist/K8000.txt" 2>&1; log "histogram at L+$EL K=$K"; fi
  ;; esac
  alive=0; for c in $SPIDS; do kill -0 $c 2>/dev/null && alive=1; done
  if [ $alive = 0 ] && [ -z "$SDONE" ]; then SDONE=$EL; log "stress done at L+$EL K=$K"; fi
  if [ -n "$SDONE" ] && [ $((EL - SDONE)) -ge 60 ]; then WHY="stress done + 60 s"; break; fi
  PM=$(stat -c %Y "$RUN/logs/poll1.log" 2>/dev/null || echo 0); GM=$(stat -c %Y "$RUN/n1/logs/gc.log" 2>/dev/null || echo 0)
  if [ $((NOW - PM)) -ge 180 ] && [ $((NOW - GM)) -ge 180 ]; then jstack $P1 > "$RUN/logs/hung-threads.txt" 2>&1; kill -9 $P1; WHY="hung"; break; fi
  [ $((EL % 10)) = 0 ] && log "L+$EL K=$K pending=$(col mut_pending) old=$(col old) unavail=$(col unavail) wr_done=$(col wr_done)"
done
log "stop: $WHY valid=$VALID"
for c in $SPIDS; do kill $c 2>/dev/null; done
sleep 2
kill -0 $P1 2>/dev/null && ALIVE=1 || ALIVE=0
stopall
for k in $(seq 1 180); do ps -eo comm,args | awk '$1=="java"' | grep -qF -- "-Dcassandra.logdir=$RUN/n1/logs" || break; sleep 1; done
grep -nF 'java.lang.OutOfMemoryError' "$RUN/n1/logs/system.log" "$RUN/n1/logs/stdout.txt" 2>/dev/null | grep -v 'JVM Arguments' > "$RUN/logs/oom-grep.txt"
log "OOM lines: $(wc -l < $RUN/logs/oom-grep.txt); first: $(head -1 $RUN/logs/oom-grep.txt | cut -c1-300)"
log "n1 hints dir at end: $(du -sb $RUN/n1/hints | cut -f1) B; n1 data $(du -sb $RUN/n1/data | cut -f1) B; shm $(du -sb $SHM | cut -f1) B"
ls -la "$DUMP" >> "$LOG"
if ls "$DUMP"/*.hprof > /dev/null 2>&1; then KEEP=0; [ "$LABEL" = T1 ] && KEEP=1; ( setsid nohup bash $H/dumpproc.sh "$RUN" $KEEP < /dev/null > /dev/null 2>&1 & ); log "dump analysis started keep=$KEEP"; fi
rm -rf "$SHM" "$RUN"/n1/{data,commitlog,hints,saved_caches,cdc_raw}
log "done alive=$ALIVE why=$WHY valid=$VALID"
echo "alive=$ALIVE why=$WHY valid=$VALID" > "$RUN/DONE"
