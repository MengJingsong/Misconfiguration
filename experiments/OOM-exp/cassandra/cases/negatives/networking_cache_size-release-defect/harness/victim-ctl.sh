#!/usr/bin/env bash
# B1 victim controller (apt140 / 10.10.1.1). One single-node Cassandra 5.0.9 per lifetime.
# Capacity settings stay at their defaults; only addresses and directories change (environment).
#   victim-ctl.sh start <label> <unmod|patched> <heap e.g. 2G> <direct e.g. 2G>   # fresh node dir
#   victim-ctl.sh ready <label>          # wait until native port answers (<= 180 s)
#   victim-ctl.sh read <label> <tag>     # one K/U reading: NMT Other, RSS, sampler last row
#   victim-ctl.sh gc <label>             # jcmd GC.run
#   victim-ctl.sh stop <label>           # stop the sampler and the JVM by PID
#   victim-ctl.sh alive <label>          # prints ALIVE/DEAD
set -uo pipefail
ROOT=/mydata/b1
IP=10.10.1.1
H=$ROOT/harness
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ cat "$(rd "$1")/cass.pid" 2>/dev/null; }

start(){
  local L=$1 B=$2 HEAP=$3 DIRECT=$4 R; R=$(rd "$L")
  local BUILD; [ "$B" = patched ] && BUILD=$ROOT/cassandra-patched || BUILD=$HOME/cassandra-b1
  rm -rf "$ROOT/node"; mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw} "$R/logs"
  rm -rf "$R/conf"; cp -r "$HOME/oom-src-pristine/conf" "$R/conf"
  local y=$R/conf/cassandra.yaml
  sed -i \
    -e "s/^listen_address: localhost/listen_address: $IP/" \
    -e "s/^rpc_address: localhost/rpc_address: $IP/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"$IP:7000\"|" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" \
    "$y"
  diff "$HOME/oom-src-pristine/conf/cassandra.yaml" "$y" > "$R/yaml.diff"
  echo "label=$L build=$BUILD heap=$HEAP direct=$DIRECT start=$(date -u +%FT%TZ)" > "$R/run.meta"
  ( cd "$BUILD" && git -C "$BUILD" diff --stat 2>/dev/null; ls -l "$BUILD"/build/apache-cassandra-*.jar; sha256sum "$BUILD"/build/apache-cassandra-*.jar ) >> "$R/run.meta" 2>&1
  CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
  CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary" \
    setsid nohup "$BUILD/bin/cassandra" -f > "$R/stdout.log" 2>&1 < /dev/null &
  echo $! > "$R/cass.pid"; sleep 3; log "started $L pid $(pid "$L") $(ps -o comm= -p $(pid "$L"))"
}

ready(){
  local L=$1 i
  for i in $(seq 1 90); do
    if grep -q "Starting listening for CQL clients" "$(rd "$L")/logs/system.log" 2>/dev/null; then
      log "ready $L"; grep -m1 "Global buffer pool limit" "$(rd "$L")/logs/system.log"
      ps -o args= -p "$(pid "$L")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory' | tr '\n' ' '; echo
      # sampler
      setsid nohup java -cp "$H" B1Sampler "$(rd "$L")/samples.csv" "$(rd "$L")/sampler.stop" 1000 \
          > "$(rd "$L")/sampler.out" 2>&1 < /dev/null &
      echo $! > "$(rd "$L")/sampler.pid"
      return 0
    fi
    alive "$L" | grep -q DEAD && { log "died during start"; return 1; }
    sleep 2
  done
  log "not ready"; return 1
}

read_(){
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L")
  local nmt rss
  local nm; nm=$(jcmd "$p" VM.native_memory summary 2>/dev/null)
  nmt=$(echo "$nm" | awk '/^-  *Other \(reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  local tot; tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null)
  sleep 1.2
  local last; last=$(grep -v ERR "$R/samples.csv" | tail -1)
  echo "$(date -u +%s),$T,${nmt:-NA},${rss:-NA},$last,${tot:-NA}" | tee -a "$R/readings.csv"
}

gc(){ jcmd "$(pid "$1")" GC.run > /dev/null 2>&1; log "GC.run $1"; }

stop(){
  local L=$1 R p sp; R=$(rd "$L"); p=$(pid "$L"); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2
  [ -n "$sp" ] && kill "$sp" 2>/dev/null
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    kill "$p"; for i in $(seq 1 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L"; pgrep -a java | grep -v grep || echo "no java left"
}

alive(){ local p; p=$(pid "$1"); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; read) read_ "$@";; gc) gc "$@";; stop) stop "$@";; alive) alive "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
