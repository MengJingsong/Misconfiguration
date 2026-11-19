#!/usr/bin/env bash
# U8 victim controller (ms0640, local), adapted from U4's victim-ctl.sh. One single-node Cassandra 5.0.9 per lifetime,
# unmodified build copied from /mydata/s4/cassandra-base, empty node dir per lifetime. Only directories change
# (environment), plus arm I (patched VectorType classes shadowing the jar through CASSANDRA_CONF, the first classpath entry).
#   victim-ctl.sh start <label> <A|I> <heap e.g. 2G> [direct e.g. 2048M | auto]   (auto = MAX_DIRECT_MEMORY_SIZE unset)
#   victim-ctl.sh ready|read <label> [tag]|hist <label> <tag>|stop|alive|oom|pid <label>
set -uo pipefail
ROOT=/mydata/s4/u8-w4
H=$ROOT/harness
BUILD=$ROOT/tree
NT="$BUILD/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/logs " | head -1; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }

start(){
  local L=$1 ARM=$2 HEAP=$3 DIRECT=${4:-auto} R; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
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
    "$y"
  case $ARM in
    A) ;;
    I) mkdir -p "$R/conf/org/apache/cassandra/db/marshal"; cp "$ROOT"/patch/org/apache/cassandra/db/marshal/VectorType*.class "$R/conf/org/apache/cassandra/db/marshal/";;
    *) log "bad arm $ARM"; return 1;;
  esac
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  local DM=15872M; [ "$DIRECT" != auto ] && DM=$DIRECT
  local MM=$(( $(mib "$HEAP") + $(mib "$DM") + 8192 ))
  local DENV=""; [ "$DIRECT" != auto ] && DENV=$DIRECT
  local XO="-Xlog:gc*=info:file=$R/gc.log:time,uptime,level,tags:filecount=5,filesize=20m -Xlog:class+load=info:file=$R/classload.log"
  [ "$(mib "$HEAP")" -gt 2048 ] && XO="$XO -XX:-HeapDumpOnOutOfMemoryError"
  echo "label=$L arm=$ARM heap=$HEAP direct=$DIRECT scopeMemoryMax=${MM}M start=$(date -u +%FT%TZ) host=$(hostname -s) arch=$(uname -m)" > "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  [ "$ARM" = I ] && sha256sum "$R"/conf/org/apache/cassandra/db/marshal/VectorType*.class >> "$R/run.meta"
  ( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DENV \
    CASSANDRA_HEAPDUMP_DIR=$R JVM_EXTRA_OPTS="$XO" \
    setsid nohup systemd-run --user --scope --unit="u8-$L-$(date +%s)" -p MemoryMax=${MM}M -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
  local i p=""; for i in $(seq 1 20); do sleep 1; p=$(pid "$L"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $L"; return 1; }
  echo "$p" > "$R/cass.pid"
  sed -n 's/^0:://p' /proc/"$p"/cgroup > "$R/cgroup.path"
  log "started $L pid $p cgroup $(cat "$R/cgroup.path")"
}

ready(){
  local L=$1 i R; R=$(rd "$L")
  for i in $(seq 1 90); do
    if grep -q "Starting listening for CQL clients" "$R/logs/system.log" 2>/dev/null; then
      log "ready $L"
      ps -o args= -p "$(pid "$L")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|AlwaysPreTouch' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
      ( setsid nohup java -Xmx64m -cp "$ROOT/cls" C2Sampler "$R/samples.csv" "$R/sampler.stop" 1000 > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
      return 0
    fi
    [ "$(alive "$L")" = DEAD ] && { log "died during start"; return 1; }
    sleep 2
  done
  log "not ready in 180 s"; return 1
}

read_(){
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L")
  local rss ra; rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null); ra=$(awk '/RssAnon/{print $2}' /proc/"$p"/status 2>/dev/null)
  local cg=/sys/fs/cgroup$(cat "$R/cgroup.path" 2>/dev/null) mc ok
  mc=$(cat "$cg/memory.current" 2>/dev/null); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events" 2>/dev/null)
  [ -f "$cg/memory.events" ] && cat "$cg/memory.events" > "$R/memory.events.last"
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,rssKB=${rss:-NA},rssAnonKB=${ra:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" | tee -a "$R/readings.csv"
}

hist(){ timeout 120 jcmd "$(pid "$1")" GC.class_histogram > "$(rd "$1")/histo-$2.txt" 2>&1; }

stop(){
  local L=$1 R p sp; R=$(rd "$L"); p=$(pid "$L"); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2
  [ -n "$sp" ] && kill "$sp" 2>/dev/null
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    timeout 120 $NT drain > "$R/drain.out" 2>&1
    kill "$p"; for i in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L"
}

alive(){ local p; p=$(cat "$(rd "$1")/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

oom(){
  local R; R=$(rd "$1")
  grep -h -m3 -B1 -A14 "java.lang.OutOfMemoryError\|OutOfDirectMemoryError" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -60
  ls -la "$R" | grep -i "hprof\|hs_err" || true
  python3 "$H/gcwin.py" "$R"
}

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; read) read_ "$@";; hist) hist "$@";;
  stop) stop "$@";; alive) alive "$@";; oom) oom "$@";; pid) pid "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
