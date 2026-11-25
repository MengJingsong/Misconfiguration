#!/usr/bin/env bash
# B26 victim controller (pc91, local), adapted from B17's victim-ctl.sh. One single-node Cassandra 5.0.9 per lifetime.
# Only the five directories change in cassandra.yaml (environment). MAX_DIRECT_MEMORY_SIZE is never set (cassandra-env.sh
# resolves it); MAX_HEAP_SIZE is explicit except heap AUTO (cassandra-env.sh resolves it for the node).
#   victim-ctl.sh start <label> <A|IV|LOAD> <heap e.g. 2G|15872M|AUTO>
#       A: build tree (unmodified); IV: build tree-iv (iv.patch); LOAD: build tree, empty node dir.
#       A/IV: a fresh cp -a of $ROOT/template. Scope: systemd-run --user --scope -p MemorySwapMax=0 (no MemoryMax).
#   victim-ctl.sh ready|read <label> [tag]|gc|hist <label> <tag>|stop|alive|oom|pid <label>
set -uo pipefail
ROOT=/mydata/s4/b26
H=$ROOT/harness
NT="$ROOT/tree/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/logs " | head -1; }

start(){
  local L=$1 ARM=$2 HEAP=$3 R BUILD; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs"
  case $ARM in A|LOAD) BUILD=$ROOT/tree;; IV) BUILD=$ROOT/tree-iv;; *) log "bad arm $ARM"; return 1;; esac
  if [ "$ARM" = LOAD ]; then mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw}
  else cp -a "$ROOT/template" "$ROOT/node" || { log "clone failed"; return 1; }; fi
  cp -r "$ROOT/conf-pristine" "$R/conf"
  local y=$R/conf/cassandra.yaml
  sed -i \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/node/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/node/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/node/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/node/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/node/cdc_raw|" \
    "$y"
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  echo "label=$L arm=$ARM build=$BUILD heap=$HEAP direct=unset(cassandra-env.sh) scope=MemorySwapMax=0 start=$(date -u +%FT%TZ) kernel=$(uname -r)" > "$R/run.meta"
  java -version 2>&1 | head -1 >> "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  local HE=""; [ "$HEAP" != AUTO ] && HE="MAX_HEAP_SIZE=$HEAP"
  ( cd "$R" && env CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs $HE CASSANDRA_HEAPDUMP_DIR=$R \
    JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Xlog:gc*=info,gc+heap=info,safepoint=info:file=$R/gc.log:time,uptime,level,tags:filecount=20,filesize=50m" \
    setsid nohup systemd-run --user --scope --unit="b26-$L-$(date +%s)" -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
  local i p=""; for i in $(seq 1 20); do sleep 1; p=$(pid "$L"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $L"; return 1; }
  echo "$p" > "$R/cass.pid"
  sed -n 's/^0:://p' /proc/"$p"/cgroup > "$R/cgroup.path"
  log "started $L pid $p cgroup $(cat "$R/cgroup.path")"
}

ready(){
  local L=$1 i R; R=$(rd "$L")
  for i in $(seq 1 60); do
    if grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null; then
      log "ready $L"
      ps -o args= -p "$(pid "$L")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
      ( setsid nohup java -Xmx64m -cp "$ROOT/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
      return 0
    fi
    [ "$(alive "$L")" = DEAD ] && { log "died during start"; return 1; }
    sleep 2
  done
  log "not ready in 120 s"; return 1
}

read_(){
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L")
  local rss; rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null)
  local cg=/sys/fs/cgroup$(cat "$R/cgroup.path" 2>/dev/null) mc ok
  mc=$(cat "$cg/memory.current" 2>/dev/null); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events" 2>/dev/null)
  [ -f "$cg/memory.events" ] && cat "$cg/memory.events" > "$R/memory.events.last"
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,rssKB=${rss:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" >> "$R/readings.csv"
}

gc(){ timeout 60 jcmd "$(pid "$1")" GC.run > /dev/null 2>&1; log "GC.run $1"; }
hist(){ timeout 180 jmap -histo:live "$(pid "$1")" > "$(rd "$1")/histo-$2.txt" 2>&1; timeout 60 jcmd "$(pid "$1")" GC.heap_info > "$(rd "$1")/heapinfo-$2.txt" 2>&1; log "histogram $1 $2"; }

stop(){
  local L=$1 R p sp; R=$(rd "$L"); p=$(cat "$R/cass.pid" 2>/dev/null); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2
  [ -n "$sp" ] && kill "$sp" 2>/dev/null
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    timeout 60 $NT tpstats > "$R/tpstats.end" 2>&1
    timeout 120 $NT drain > "$R/drain.out" 2>&1
    kill "$p"; for i in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L"
}

alive(){ local p; p=$(cat "$(rd "$1")/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

oom(){
  local R; R=$(rd "$1")
  grep -h -m3 -B1 -A14 "java\.lang\.OutOfMemoryError: \|OutOfDirectMemoryError" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -60
  ls -la "$R" | grep -i "hprof\|hs_err" || true
  python3 "$H/gcwin.py" "$R"
}

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; read) read_ "$@";; gc) gc "$@";; hist) hist "$@";;
  stop) stop "$@";; alive) alive "$@";; oom) oom "$@";; pid) pid "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
