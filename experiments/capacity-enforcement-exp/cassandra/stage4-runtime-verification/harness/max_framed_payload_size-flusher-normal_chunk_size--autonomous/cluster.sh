#!/usr/bin/env bash
# o132 cluster tier (case file B3e, with the 2026-11-25 amendment for the unpaused control).
# One node on ms0625, patched build in $W/src, data in $W/data, pausing proxy 19042 -> 9042.
set -uo pipefail
W=${W:-/mydata/jingsong-cass-s4/o132}
LOG=$W/logs/cluster.log
mkdir -p $W/logs/cluster $W/data
exec > >(tee -a "$LOG") 2>&1
cd $W/src
CLASSPATH=$(cat $W/classpath.txt)
CJ="$(grep -hv '^\s*#' $W/src/conf/jvm-clients.options $W/src/conf/jvm11-clients.options | grep -v '^\s*$' | tr '\n' ' ') -XX:MaxDirectMemorySize=2g -Dio.netty.tryReflectionSetAccessible=true"
ulimit -n 100000 || true
ts() { date +%s%3N; }
run() { echo "+ [$(ts)] $*"; "$@"; }
SYSLOG=$W/src/logs/system.log

stop_node() {
  [ -f $W/cassandra.pid ] || return 0
  local p; p=$(cat $W/cassandra.pid)
  if ps -p $p >/dev/null 2>&1; then
    run kill $p
    for i in $(seq 1 120); do ps -p $p >/dev/null 2>&1 || break; sleep 1; done
    ps -p $p >/dev/null 2>&1 && { echo "node $p did not exit; kill -9"; kill -9 $p; sleep 2; }
  fi
  rm -f $W/cassandra.pid
  echo "node stopped [$(ts)]"
}
cleanup() {
  echo "=== cleanup [$(ts)]"
  stop_node
  [ -f $W/proxy.pid ] && { kill $(cat $W/proxy.pid) 2>/dev/null; rm -f $W/proxy.pid; }
  rm -f $W/pause.flag
  pkill -u $(id -u) -f 'ClusterProbe' 2>/dev/null || true
}
trap cleanup EXIT

set_yaml() { # cache_mib
  python3 - "$W" "$1" <<'EOF'
import sys, re
W, cache = sys.argv[1], sys.argv[2]
f = W + "/src/conf/cassandra.yaml"
t = open(f).read()
def setkey(t, key, val):
    pat = re.compile(r'^#?\s*' + re.escape(key) + r':.*(\n(\s+-\s.*|#?\s+-\s.*))*', re.M)
    new = key + ": " + val
    if pat.search(t):
        return pat.sub(lambda m: new, t, count=1)
    return t + "\n" + new + "\n"
t = setkey(t, "data_file_directories", "\n    - " + W + "/data/data")
t = setkey(t, "commitlog_directory", W + "/data/commitlog")
t = setkey(t, "saved_caches_directory", W + "/data/saved_caches")
t = setkey(t, "hints_directory", W + "/data/hints")
t = setkey(t, "cdc_raw_directory", W + "/data/cdc")
t = setkey(t, "networking_cache_size", cache + "MiB")
open(f, "w").write(t)
EOF
  grep -nE '^(data_file_directories|    - /mydata|commitlog_directory|saved_caches_directory|hints_directory|cdc_raw_directory|networking_cache_size|native_transport_port|storage_port):' $W/src/conf/cassandra.yaml
  grep -nE '^    - /mydata' $W/src/conf/cassandra.yaml
}

start_node() { # K cache
  local K=$1 cache=$2
  set_yaml $cache
  SYSLINE=$( [ -f $SYSLOG ] && wc -l < $SYSLOG || echo 0 )
  echo "=== start node K=${K:-unset} cache=${cache}MiB [$(ts)] syslog line $SYSLINE"
  ( export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M
    export JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary ${K:+-Dcassandra.test.max_framed_payload_size=$K}"
    echo "+ [$(ts)] JVM_EXTRA_OPTS=$JVM_EXTRA_OPTS bin/cassandra -p $W/cassandra.pid"
    bin/cassandra -p $W/cassandra.pid > $W/logs/cluster/out-K${K:-unset}-c$cache.log 2>&1 )
  for i in $(seq 1 240); do
    sleep 2
    if [ -f $W/cassandra.pid ] && ! ps -p $(cat $W/cassandra.pid) >/dev/null 2>&1; then echo "node died during start"; tail -30 $SYSLOG; exit 3; fi
    tail -n +$((SYSLINE+1)) $SYSLOG 2>/dev/null | grep -q 'Starting listening for CQL clients' && break
  done
  tail -n +$((SYSLINE+1)) $SYSLOG | grep -q 'Starting listening for CQL clients' || { echo "node not listening after 480 s"; exit 3; }
  for i in $(seq 1 60); do bin/nodetool statusbinary 2>/dev/null | grep -q running && break; sleep 2; done
  run bin/nodetool status
  run bin/nodetool statusbinary
  echo "node up [$(ts)] pid $(cat $W/cassandra.pid)"
}

check_k() { # expected K
  local want=$1
  local got; got=$(tail -n +$((SYSLINE+1)) $SYSLOG | grep -o 'MAX_FRAMED_PAYLOAD_SIZE=[0-9]*' | sort -u | tr '\n' ' ')
  echo "KCHECK want=$want got=$got" | tee -a $W/cluster.csv
  tail -n +$((SYSLINE+1)) $SYSLOG | grep 'MAX_FRAMED_PAYLOAD_SIZE=' | sed 's/^/KLINE,/' | tee -a $W/cluster.csv
}

read_cell() { # tag M K mode(pause|nopause) rep
  local tag=$1 M=$2 K=$3 mode=$4 rep=$5
  local f=$W/logs/cluster/read-$tag-rep$rep.log
  echo "=== read $tag M=$M K=${K:-unset} mode=$mode rep=$rep [$(ts)]"
  echo "CELL,$tag,K=${K:-unset},M=$M,mode=$mode,rep=$rep,t=$(ts)" >> $W/cluster.csv
  rm -f $W/pause.flag
  local extra=""; [ "$mode" = nopause ] && extra=nopause
  java $CJ -cp "$W/probe/classes:$CLASSPATH" ClusterProbe read 19042 $M 4194304 7199 $W/pause.flag 5000 $extra > $f 2>&1 &
  local pp=$!
  # held-window supporting readings: 2.5 s after the pause flag appears (or after the baseline sample for nopause)
  for i in $(seq 1 300); do
    if [ "$mode" = pause ]; then [ -f $W/pause.flag ] && break; else grep -q 'SAMPLE,baseline' $f && break; fi
    ps -p $pp >/dev/null || break; sleep 0.1
  done
  sleep 2.5
  { echo "--- held-window readings t=$(ts)"
    ss -tmi '( sport = :9042 )'
    jcmd $(cat $W/cassandra.pid) VM.native_memory summary | grep -A2 -E 'Other|Internal'
    grep VmRSS /proc/$(cat $W/cassandra.pid)/status; } > $W/logs/cluster/held-$tag-rep$rep.txt 2>&1
  local sendq; sendq=$(ss -tn '( sport = :9042 )' | awk 'NR>1{s+=$3} END{print s+0}')
  wait $pp; local rc=$?
  grep -E 'SAMPLE|RESULT' $f | tee -a $W/cluster.csv
  echo "SUPPORT,sendQ_9042=$(grep -A0 ESTAB $W/logs/cluster/held-$tag-rep$rep.txt | awk '{s+=$3} END{print s+0}'),$(grep VmRSS $W/logs/cluster/held-$tag-rep$rep.txt | tr -s ' ' | tr ' ' '=')" | tee -a $W/cluster.csv
  [ $rc -eq 0 ] || { echo "probe rc=$rc"; tail -20 $f; }
}

echo "=== cluster.sh start $(date) on $(hostname) $(uname -m)"
run sysctl net.ipv4.tcp_wmem net.ipv4.tcp_rmem
run ss -ltn
: > $W/cluster.csv

# 1. K unset, cache 512 MiB: load, main M=32, positive control 1 (M=64), unpaused control.
start_node "" 512
run java $CJ -cp "$W/probe/classes:$CLASSPATH" ClusterProbe load 9042 64 4194304 > $W/logs/cluster/load.log 2>&1 || { echo load failed; tail -30 $W/logs/cluster/load.log; exit 4; }
run bin/nodetool flush probe
run du -sh $W/data
python3 $W/probe/pause-proxy.py 19042 9042 $W/pause.flag > $W/logs/cluster/proxy.log 2>&1 &
echo $! > $W/proxy.pid; echo "proxy pid $(cat $W/proxy.pid)"; sleep 1
for rep in 1 2 3; do read_cell main-K131060 32 "" pause $rep; done
check_k 131060
for rep in 1 2 3; do read_cell pc1-M64 64 "" pause $rep; done
for rep in 1 2 3; do read_cell unpaused 32 "" nopause $rep; done
stop_node
# 2. K = 65536, 16384, 4096 (cache 512 MiB), M=32.
for K in 65536 16384 4096; do
  start_node $K 512
  for rep in 1 2 3; do read_cell main-K$K 32 $K pause $rep; done
  check_k $K
  stop_node
done
# 3. Positive control 2: K unset, cache 32 MiB, M=32.
start_node "" 32
for rep in 1 2 3; do read_cell pc2-cache32 32 "" pause $rep; done
check_k 131060
stop_node
set_yaml 512 >/dev/null
echo "=== cluster.sh done $(date)"
