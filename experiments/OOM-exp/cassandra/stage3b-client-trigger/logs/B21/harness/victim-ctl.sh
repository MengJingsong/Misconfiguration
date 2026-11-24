#!/usr/bin/env bash
# B21 3-b confirm (pc72, 2026-11-23): stage-2 victim-ctl.sh with ROOT=/mydata/s4/3b-B21 and the arms AUTH / LOAD-AUTH
# (authentication + authorization on; every capacity constraint at its default). Stage-2 arms A / I / LOAD kept unchanged.
#   arm AUTH: A + authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer, role_manager: CassandraRoleManager
#   arm LOAD-AUTH: empty node dir, same auth lines (the setup + load lifetime; not a reading)
# Stage-2 header:
# B21 victim controller (ms0604, local), adapted from B17's victim-ctl.sh. One single-node Cassandra 5.0.9 per lifetime,
# unmodified build copied from /mydata/s4/cassandra-base. Only directories change (environment), plus arm I.
#   arm A: shipped defaults (read thresholds off)
#   arm I: A + read_thresholds_enabled: true + local_read_size_fail_threshold: 64MiB (intervention)
#   arm LOAD: empty node dir (the load lifetime; not a reading)
#   victim-ctl.sh start <label> <A|I|LOAD> <heap e.g. 2G|15872M>   MAX_DIRECT_MEMORY_SIZE unset (cassandra-env.sh resolves it)
#       Scope: systemd-run --user --scope -p MemoryMax=<heap + 15872M + 6G> -p MemorySwapMax=0 (isolation only; amendment A1
#       2026-11-21: the resolved MaxDirectMemorySize is 15,872 MiB, not the 7,936 MiB of the design)
#       NODUMP=1 in the environment: -XX:-HeapDumpOnOutOfMemoryError (disk plan: heaps >= 8 GiB without room for the dump)
#   victim-ctl.sh ready|read <label> [tag]|gc|hist <label> <tag>|stop|alive|oom|pid <label>
set -uo pipefail
ROOT=/mydata/s4/3b-B21
H=$ROOT/harness
BUILD=$ROOT/tree
NT="$BUILD/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/logs " | head -1; }
mib(){ case $1 in *G) echo $(( ${1%G} * 1024 ));; *M) echo ${1%M};; esac; }

start(){
  local L=$1 ARM=$2 HEAP=$3 R; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs"
  if [ "$ARM" = LOAD ] || [ "$ARM" = LOAD-AUTH ]; then mkdir -p "$ROOT/node"/{data,commitlog,hints,saved_caches,cdc_raw}
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
  case $ARM in
    A|LOAD) ;;
    AUTH|LOAD-AUTH) sed -i -e 's|^authenticator: AllowAllAuthenticator$|authenticator: PasswordAuthenticator|' \
                          -e 's|^authorizer: AllowAllAuthorizer$|authorizer: CassandraAuthorizer|' \
                          -e 's|^role_manager: .*$|role_manager: CassandraRoleManager|' "$y";;
    I) printf '# B21 arm I (intervention): the byte control that ships off, switched on\nread_thresholds_enabled: true\nlocal_read_size_fail_threshold: 64MiB\n' >> "$y";;
    *) log "bad arm $ARM"; return 1;;
  esac
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  local MM=$(( $(mib "$HEAP") + 15872 + 6144 ))M
  echo "label=$L arm=$ARM heap=$HEAP nodump=${NODUMP:-0} direct=unset(resolved by cassandra-env.sh) scope=MemoryMax=$MM,MemorySwapMax=0 start=$(date -u +%FT%TZ) kernel=$(uname -r) arch=$(uname -m)" > "$R/run.meta"
  java -version 2>&1 | head -1 >> "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  ( cd "$R" && unset MAX_DIRECT_MEMORY_SIZE HEAP_NEWSIZE; CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP \
    CASSANDRA_HEAPDUMP_DIR=$R \
    JVM_EXTRA_OPTS="${NODUMP:+-XX:-HeapDumpOnOutOfMemoryError }-XX:NativeMemoryTracking=summary -Xlog:gc*,safepoint:file=$R/gc.log:time,uptime,level,tags:filecount=20,filesize=20m" \
    setsid nohup systemd-run --user --scope --unit="b3b21-$L-$(date +%s)" -p MemoryMax=$MM -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$R/stdout.log" 2>&1 & )
  local i p=""; for i in $(seq 1 30); do sleep 1; p=$(pid "$L"); [ -n "$p" ] && break; done
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
      ps -o args= -p "$(pid "$L")" | tr ' ' '\n' | grep -E '^-Xm[sx]|^-Xmn|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|max_top_k' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
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
  echo "$(date -u +%s),$T,rssKB=${rss:-NA},rssAnonKB=${ra:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" >> "$R/readings.csv"
}

gc(){ timeout 60 jcmd "$(pid "$1")" GC.run > /dev/null 2>&1; log "GC.run $1"; }
hist(){ timeout 120 jcmd "$(pid "$1")" GC.class_histogram > "$(rd "$1")/histo-$2.txt" 2>&1; log "histogram $1 $2"; }

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
  grep -h -m3 -B1 -A14 "java.lang.OutOfMemoryError\|OutOfDirectMemoryError" "$R/logs/system.log" "$R/stdout.log" 2>/dev/null | head -60
  ls -la "$R" | grep -i "hprof\|hs_err" || true
  python3 "$H/gcwin.py" "$R"
}

cmd=$1; shift
case $cmd in
  start) start "$@";; ready) ready "$@";; read) read_ "$@";; gc) gc "$@";; hist) hist "$@";;
  stop) stop "$@";; alive) alive "$@";; oom) oom "$@";; pid) pid "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
