#!/usr/bin/env bash
# U9 victim controller (pc91, local to the node), adapted from U4's victim-ctl.sh. One single-node Cassandra 5.0.9
# per lifetime, unmodified build copied from /mydata/s4/cassandra-base. Only directories and auto_snapshot change
# (environment), plus arm I (column_index_size: 4MiB, intervention).
#   victim-ctl.sh start <label> <arm T|C|I|S|M|B> <heap e.g. 2G> <direct e.g. 1024M>
#   victim-ctl.sh ready|stop|alive|pid <label>
# Launch: setsid nohup systemd-run --user --scope -p MemorySwapMax=0 (no MemoryMax: the budget is the heap).
set -uo pipefail
ROOT=/mydata/s4/u9-w4
BUILD=$ROOT/tree
NT="$BUILD/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/logs " | head -1; }

start(){
  local L=$1 ARM=$2 HEAP=$3 DIRECT=$4 R; R=$(rd "$L")
  local jp; for jp in $(pgrep -x java); do
    if tr '\0' ' ' < /proc/$jp/cmdline 2>/dev/null | grep -q 'org.apache.cassandra.service.CassandraDaemon'; then log "REFUSE: a CassandraDaemon is already running (pid $jp)"; return 1; fi
  done
  rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs" "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw}
  cp -r "$ROOT/conf-pristine" "$R/conf"
  local y=$R/conf/cassandra.yaml
  sed -i \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" \
    -e "s|^auto_snapshot: true|auto_snapshot: false|" \
    "$y"
  case $ARM in
    T|C|S|M|B) ;;
    I) printf '# U9 arm I (intervention): the index granularity the shipped yaml recommends for large rows\ncolumn_index_size: 4MiB\n' >> "$y";;
    *) log "bad arm $ARM"; return 1;;
  esac
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  echo "label=$L arm=$ARM heap=$HEAP direct=$DIRECT start=$(date -u +%FT%TZ)" > "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  ( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
    CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="-Dcassandra.printHeapHistogramOnOutOfMemoryError=true" \
    setsid nohup systemd-run --user --scope --unit="u9-$L-$(date +%s)" -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
  local i p=""; for i in $(seq 1 20); do sleep 1; p=$(pid "$L"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $L"; return 1; }
  echo "$p" > "$R/cass.pid"
  log "started $L pid $p"
}

ready(){
  local L=$1 i R; R=$(rd "$L")
  for i in $(seq 1 90); do
    if grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null; then
      log "ready $L"
      ps -o args= -p "$(pid "$L")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|printHeapHistogram|Xlog:gc' | tr '\n' ' ' | sed 's/^/resolved: /' >> "$R/run.meta"; echo >> "$R/run.meta"
      grep -h -E "concurrent_compactors=|memtable_heap_space=|memtable_flush_writers=|column_index_size=|column_index_cache_size=|memtable_cleanup_threshold=|compaction_throughput=" "$R/logs/system.log" | head -1 | tr ';' '\n' | grep -oE "(concurrent_compactors|memtable_heap_space|memtable_offheap_space|memtable_flush_writers|memtable_cleanup_threshold|column_index_size|column_index_cache_size|compaction_throughput|partition_size_fail_threshold|auto_snapshot|memtable_allocation_type)=[^,]*" | sed 's/^/config: /' >> "$R/run.meta"
      grep -h "Heap size:\|Global memtable" "$R/logs/system.log" | head -3 | sed 's/^/log: /' >> "$R/run.meta"
      return 0
    fi
    [ "$(alive "$L")" = DEAD ] && { log "died during start"; return 1; }
    sleep 2
  done
  log "not ready in 180 s"; return 1
}

stop(){
  local L=$1 R p; R=$(rd "$L"); p=$(cat "$R/cass.pid" 2>/dev/null)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    timeout 120 $NT drain > "$R/drain.out" 2>&1
    kill "$p"; for i in $(seq 1 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L"
}

alive(){ local p; p=$(cat "$(rd "$1")/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; stop) stop "$@";; alive) alive "$@";; pid) pid "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
