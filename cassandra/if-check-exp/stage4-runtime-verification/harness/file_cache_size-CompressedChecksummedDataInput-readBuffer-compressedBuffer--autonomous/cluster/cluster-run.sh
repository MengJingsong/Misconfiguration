#!/usr/bin/env bash
# usage: cluster-run.sh <label> <threshold-MiB> <compress yes|no> <hints|control>
# Runs on pc07, tree ~/s4-fc, loopback 127.0.12.1-3, JMX 7212/7213/7214, native 9144, storage 7012.
# EXPECTED lines are checked as the run goes; the run stops (and stops all nodes) on the first failed check.
set -u
LABEL=$1; TH=$2; COMP=$3; MODE=$4
HD=$(cd "$(dirname "$0")" && pwd)
TREE=$HOME/s4-fc; RD=$HOME/s4-fc-run/$LABEL; LG=$HOME/s4-fc-logs/cluster/$LABEL
N=${N_ROWS:-100}; BLOB=$((6*1024*1024))
rm -rf $RD; mkdir -p $RD $LG
exec > >(tee -a $LG/run.log) 2>&1
ulimit -n 100000
log() { echo "$(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
nt() { local idx=$1; shift; $TREE/bin/nodetool -h 127.0.0.1 -p $( [ $idx = 1 ] && echo 7212 || echo $((7410+idx)) ) "$@"; }
pidof_n() { cat $RD/n$1/pid 2>/dev/null; }
alive() { local p; p=$(pidof_n $1); [ -n "$p" ] && kill -0 $p 2>/dev/null; }
start_node() {
  local idx=$1 extra=""
  python3 $HD/gen-conf.py $TREE $RD $idx $( [ $idx = 1 ] && echo $TH || echo none ) $COMP || return 1
  [ $idx = 1 ] && extra="-XX:MaxDirectMemorySize=4g"
  log "start node $idx"
  ( cd $TREE; CASSANDRA_CONF=$RD/n$idx/conf CASSANDRA_LOG_DIR=$RD/n$idx/logs MAX_HEAP_SIZE=2G \
    JVM_EXTRA_OPTS="-Dcassandra.ring_delay_ms=5000 -Dcassandra.skip_sync=true $extra" \
    setsid nohup bin/cassandra -p $RD/n$idx/pid < /dev/null > $RD/n$idx/logs/stdout.log 2>&1 & )
}
wait_up() { # node idx, via node $2's nodetool; wait until 'UN' count == $3
  local idx=$1 want=$2 i
  for i in $(seq 1 90); do
    alive $idx || { [ $i -gt 5 ] && { log "node $idx died"; return 1; }; }
    if [ "$(nt $idx status 2>/dev/null | grep -c '^UN')" = "$want" ] && [ "$(nt $idx statusbinary 2>/dev/null)" = running ]; then log "node $idx up ($want UN)"; return 0; fi
    sleep 3
  done
  log "timeout waiting for node $idx"; return 1
}
stop_node() {
  local idx=$1 p; p=$(pidof_n $idx); [ -z "$p" ] && return 0
  nt $idx drain >/dev/null 2>&1
  kill $p 2>/dev/null
  for i in $(seq 1 40); do kill -0 $p 2>/dev/null || break; sleep 1; done
  kill -0 $p 2>/dev/null && kill -9 $p
  log "node $idx stopped (pid $p)"
}
SAMPLER_PID=""
cleanup() {
  [ -n "$SAMPLER_PID" ] && kill $SAMPLER_PID 2>/dev/null
  for i in 3 2 1; do stop_node $i; done
  log "cleanup done; leftovers: $(ps -eo pid,cmd | grep "[C]assandraDaemon" | grep -c "$RD")"
}
trap cleanup EXIT
fail() { log "EXPECTED-FAILED: $*"; exit 2; }

mkdir -p $LG/classes; ( javac -d $LG/classes $HD/Sampler.java ) || fail "sampler compile"

start_node 1 || fail "start n1"; wait_up 1 1 || fail "n1 up"
grep -h "Global buffer pool limit" $RD/n1/logs/system.log | sed "s/^/EVIDENCE /"
EXP="Global buffer pool limit is $(python3 -c "print(('%dMiB' % $TH) if $TH<1024 else '')")"
grep -q "limit is ${TH}MiB for chunk-cache\|limit is ${TH}.00 MiB for chunk-cache\|limit is ${TH}\.0*MiB for chunk-cache" $RD/n1/logs/system.log || log "NOTE: pool-limit log text not matched literally; check EVIDENCE line above"
CAP=$(nt 1 sjk mx -mg -b 'org.apache.cassandra.metrics:type=BufferPool,scope=chunk-cache,name=Capacity' -f Value 2>/dev/null | tr -d ' \r\n' | grep -o '[0-9]*$')
log "Capacity metric: $CAP"
[ "$CAP" = "$((TH*1024*1024))" ] || fail "Capacity metric $CAP != $((TH*1024*1024))"

if [ $MODE = hints ]; then
  start_node 2 || fail "start n2"; wait_up 1 2 || fail "n2 up"
  start_node 3 || fail "start n3"; wait_up 1 3 || fail "n3 up"
  python3 $HD/write_blobs.py 127.0.12.1 9144 0 0 1 || fail "schema"
  sleep 5
  for i in 3 2; do stop_node $i; done
  for k in $(seq 1 40); do [ "$(nt 1 status 2>/dev/null | grep -c '^DN')" = 2 ] && break; sleep 2; done
  [ "$(nt 1 status 2>/dev/null | grep -c '^DN')" = 2 ] || fail "node1 does not see 2 DN"
  log "nodes 2,3 down (as seen by node 1)"
  # settle: probe writes until prompt
  PID1=$(pidof_n 1)
  java -cp $LG/classes Sampler 127.0.0.1 7212 $PID1 $LG/sampler.csv 500 > $LG/sampler.out 2>&1 & SAMPLER_PID=$!
  sleep 5
  T_WRITE0=$(date +%s%3N); log "write phase start"
  python3 $HD/write_blobs.py 127.0.12.1 9144 $N $BLOB 0 > $LG/write.log 2>&1 || fail "write phase"
  T_WRITE1=$(date +%s%3N); log "write phase end"; tail -1 $LG/write.log
  sleep 8
  ls -l $RD/n1/hints > $LG/hints-after-write.txt; NF=$(ls $RD/n1/hints | grep -c '\.hints$'); du -sb $RD/n1/hints | tee $LG/hints-bytes-after-write.txt
  log "hints files after write: $NF"
  [ "$NF" -ge 2 ] || fail "no hints files after write ($NF)"
  grep -c "Compress" $RD/n1/hints/*.hints >/dev/null 2>&1
  T_DISP0=$(date +%s%3N); log "dispatch phase start (start n2, n3)"
  start_node 2; start_node 3
  for k in $(seq 1 400); do
    NL=$(ls $RD/n1/hints 2>/dev/null | grep -c '\.hints$'); [ "$NL" = 0 ] && break; sleep 3
  done
  T_DISP1=$(date +%s%3N); log "hints dir empty after $(( (T_DISP1-T_DISP0)/1000 )) s (files left: $NL)"
  [ "$NL" = 0 ] || fail "hints not drained"
  sleep 60
  T_END=$(date +%s%3N)
  echo "T_WRITE0=$T_WRITE0 T_WRITE1=$T_WRITE1 T_DISP0=$T_DISP0 T_DISP1=$T_DISP1 T_END=$T_END hints_files=$NF" > $LG/phases.txt
  kill $SAMPLER_PID; SAMPLER_PID=""
  python3 $HD/summarize.py $LG/sampler.csv $T_DISP0 $T_END > $LG/summary-dispatch.txt
  python3 $HD/summarize.py $LG/sampler.csv $T_WRITE0 $T_WRITE1 > $LG/summary-write.txt
  grep -h "Maximum memory usage reached" $RD/n1/logs/system.log | head -3 | sed "s/^/EVIDENCE /"
  grep -hc "Hints.*delivered\|Finished hinted handoff" $RD/n1/logs/system.log | sed "s/^/EVIDENCE delivered-lines /"
  cp $RD/n1/logs/system.log $LG/n1-system.log
else
  # control: single node, sampler from before the write; stress write, flush, stress read
  PID1=$(pidof_n 1)
  S="$TREE/tools/bin/cassandra-stress"
  java -cp $LG/classes Sampler 127.0.0.1 7212 $PID1 $LG/sampler.csv 500 > $LG/sampler.out 2>&1 & SAMPLER_PID=$!
  sleep 5
  T_R0=$(date +%s%3N); log "write phase start"
  $S write n=200000 cl=ONE -col n=FIXED\(3\) size=FIXED\(1024\) -rate threads=50 -node 127.0.12.1 -port native=9144 > $LG/stress-write.log 2>&1 || fail "stress write"
  grep -E "^Total errors|Op rate" $LG/stress-write.log | head -3
  nt 1 flush >/dev/null 2>&1
  log "read phase start"
  $S read duration=120s no-warmup cl=ONE -pop dist=UNIFORM\(1..200000\) -col n=FIXED\(3\) size=FIXED\(1024\) -rate threads=100 -node 127.0.12.1 -port native=9144 > $LG/stress-read.log 2>&1 || fail "stress read"
  T_R1=$(date +%s%3N); log "read phase end"
  grep -E "^Total errors|Op rate|Total partitions" $LG/stress-read.log | head -4
  sleep 5; kill $SAMPLER_PID; SAMPLER_PID=""
  echo "T_R0=$T_R0 T_R1=$T_R1" > $LG/phases.txt
  python3 $HD/summarize.py $LG/sampler.csv $T_R0 $T_R1 > $LG/summary-read.txt
  grep -h "Maximum memory usage reached" $RD/n1/logs/system.log | head -2 | sed "s/^/EVIDENCE /"
  cp $RD/n1/logs/system.log $LG/n1-system.log
fi
log "run complete"
# data dirs removed after cleanup trap
trap 'cleanup; rm -rf $RD' EXIT
exit 0
