#!/usr/bin/env bash
# C2 victim controller (apt140 / 10.10.1.1), adapted from B1's victim-ctl.sh. One single-node Cassandra 5.0.9
# per lifetime, unmodified build ~/cassandra-b1. Only addresses and directories change (environment), plus:
#   arm A: nothing else (read thresholds at their defaults: disabled/unset = unprotected configuration)
#   arm B: read_thresholds_enabled + the test/conf/cassandra.yaml values (accepted enabled value)
#   modifiers (intervention arms only), appended with '+': R<n> = native_transport_rate_limiting_enabled +
#   native_transport_max_requests_per_second n;  T<n> = native_transport_max_threads n.  e.g. B+R30, A+T32
#   victim-ctl.sh start <label> <A|B[+mod...]> <heap e.g. 2G | auto> [direct e.g. 7936M]   # fresh node dir;
#     heap auto = MAX_HEAP_SIZE unset (cassandra-env.sh resolves 1/2 RAM); direct omitted = resolved by cassandra-env.sh (1/4 RAM)
#   victim-ctl.sh ready|read <label> [tag]|gc|hist|flush|stop|alive|oom <label>
set -uo pipefail
ROOT=/mydata/c2
IP=10.10.1.1
H=$ROOT/harness
BUILD=$HOME/cassandra-b1
log(){ echo "[$(date -u '+%FT%TZ')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ cat "$(rd "$1")/cass.pid" 2>/dev/null; }

start(){
  local L=$1 ARM=$2 HEAP=$3 DIRECT=${4:-} R; R=$(rd "$L")
  [ "$HEAP" = auto ] && HEAP=""
  pgrep -f CassandraDaemon >/dev/null && { log "REFUSE: a CassandraDaemon is already running"; pgrep -af CassandraDaemon | cut -c1-120; return 1; }
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
  local BASE=${ARM%%+*} MODS=""; [[ $ARM == *+* ]] && MODS=${ARM#*+}
  case $BASE in
    A) ;;
    B) cat >> "$y" <<'EOF'
# C2 arm B: read thresholds enabled at the project's test/conf/cassandra.yaml values
read_thresholds_enabled: true
coordinator_read_size_warn_threshold: 1024KiB
coordinator_read_size_fail_threshold: 4096KiB
local_read_size_warn_threshold: 4096KiB
local_read_size_fail_threshold: 8192KiB
row_index_read_size_warn_threshold: 4096KiB
row_index_read_size_fail_threshold: 8192KiB
EOF
       ;;
    *) log "bad arm $ARM"; return 1;;
  esac
  local m
  for m in ${MODS//+/ }; do
    case $m in
      R*) printf '# C2 intervention: native request rate cap\nnative_transport_rate_limiting_enabled: true\nnative_transport_max_requests_per_second: %s\n' "${m#R}" >> "$y";;
      T*) printf '# C2 intervention: native request threads\nnative_transport_max_threads: %s\n' "${m#T}" >> "$y";;
      *) log "bad modifier $m"; return 1;;
    esac
  done
  diff "$HOME/oom-src-pristine/conf/cassandra.yaml" "$y" > "$R/yaml.diff"
  echo "label=$L arm=$ARM build=$BUILD heap=${HEAP:-auto} direct=${DIRECT:-auto} start=$(date -u +%FT%TZ)" > "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
  CASSANDRA_HEAPDUMP_DIR=$R \
  JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Xlog:gc=info,safepoint=info:file=$R/gc.log:time,uptime,level,tags:filecount=20,filesize=20m" \
    setsid nohup "$BUILD/bin/cassandra" -f > "$R/stdout.log" 2>&1 < /dev/null &
  echo $! > "$R/cass.pid"; sleep 3; log "started $L pid $(pid "$L") $(ps -o comm= -p "$(pid "$L")")"
}

ready(){
  local L=$1 i R; R=$(rd "$L")
  for i in $(seq 1 90); do
    if grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null; then
      log "ready $L"
      ps -o args= -p "$(pid "$L")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory' | tr '\n' ' ' | tee -a "$R/run.meta"; echo
      setsid nohup java -Xmx64m -cp "$H" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 > "$R/sampler.out" 2>&1 < /dev/null &
      echo $! > "$R/sampler.pid"
      return 0
    fi
    alive "$L" | grep -q DEAD && { log "died during start"; return 1; }
    sleep 2
  done
  log "not ready"; return 1
}

read_(){
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L")
  local nm; nm=$(timeout 20 jcmd "$p" VM.native_memory summary 2>/dev/null)
  local oth tot hp
  oth=$(echo "$nm" | awk '/^-  *Other \(reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  local rss; rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null)
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,nmtOtherKB=${oth:-NA},nmtTotalKB=${tot:-NA},rssKB=${rss:-NA},$last" | tee -a "$R/readings.csv"
}

gc(){ timeout 60 jcmd "$(pid "$1")" GC.run > /dev/null 2>&1; log "GC.run $1"; }
hist(){ timeout 120 jcmd "$(pid "$1")" GC.class_histogram > "$(rd "$1")/histo-$2.txt" 2>&1; head -25 "$(rd "$1")/histo-$2.txt"; }
flush(){ "$BUILD/bin/nodetool" -h 127.0.0.1 flush c2 && log "flushed"; "$BUILD/bin/nodetool" -h 127.0.0.1 tablestats c2.t 2>/dev/null | grep -E "SSTable count|Space used \(live\)|Compacted partition maximum"; }

stop(){
  local L=$1 R p sp; R=$(rd "$L"); p=$(pid "$L"); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2
  [ -n "$sp" ] && kill "$sp" 2>/dev/null
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    kill "$p"; for i in $(seq 1 40); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L"; pgrep -af java | grep -v grep | cut -c1-120 || echo "no java left"
}

alive(){ local p; p=$(pid "$1"); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

oom(){
  local R; R=$(rd "$1")
  grep -h -m3 -B1 -A12 "java.lang.OutOfMemoryError\|OutOfDirectMemoryError" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -60
  ls -la "$R" | grep -i "hprof\|hs_err" || true
  sudo dmesg -T 2>/dev/null | grep -i "killed process\|oom-kill" | tail -2 || true
  python3 "$H/gcwin.py" "$R"
}

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; read) read_ "$@";; gc) gc "$@";; hist) hist "$@";; flush) flush "$@";;
  stop) stop "$@";; alive) alive "$@";; oom) oom "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
