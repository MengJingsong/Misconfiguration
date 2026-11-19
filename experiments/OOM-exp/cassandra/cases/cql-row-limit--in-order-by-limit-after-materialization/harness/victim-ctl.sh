#!/usr/bin/env bash
# B17 victim controller (pc72, local), adapted from U4's victim-ctl.sh. One single-node Cassandra 5.0.9 per lifetime,
# unmodified build copied from /mydata/s4/cassandra-base. Only directories change (environment), plus arm I2.
#   arm A: shipped defaults (read thresholds off)
#   arm I2: A + read_thresholds_enabled: true + local_read_size_fail_threshold: 64MiB (optional intervention)
#   victim-ctl.sh start <label> <A|I2|LOAD> <heap e.g. 2G|31744M> <direct e.g. 1024M>   (explicit, never auto)
#       LOAD: empty node dir; otherwise a fresh cp -a of $ROOT/template.
#       Scope: systemd-run --user --scope -p MemorySwapMax=0 (no MemoryMax: amendment 2026-11-18, no container budget)
#   victim-ctl.sh ready|read <label> [tag]|gc|hist <label> <tag>|stop|alive|oom|pid <label>
set -uo pipefail
ROOT=/mydata/s4/b17-w4
H=$ROOT/harness
BUILD=$ROOT/tree
NT="$BUILD/bin/nodetool -h 127.0.0.1"
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/logs " | head -1; }

start(){
  local L=$1 ARM=$2 HEAP=$3 DIRECT=$4 R; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  rm -rf "$ROOT/node" "$R"; mkdir -p "$R/logs"
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
  case $ARM in
    A) ;;
    LOAD|FILL) # amendment 2026-11-18 13:58 EST: pc72's /mydata is a spinning RAID (PERC H710P, ROTA=1); the first LOAD stalled
          # (commit-log sync 51.9 s, 23 inserts failed after 5 retries). LOAD only: commit log on tmpfs. Not a reading.
          rm -rf /dev/shm/b17-w4-commitlog; mkdir -p /dev/shm/b17-w4-commitlog
          sed -i "s|^commitlog_directory: .*|commitlog_directory: /dev/shm/b17-w4-commitlog|" "$y";;
    I2) printf '# B17 arm I2 (optional intervention): the byte control that ships off, switched on\nread_thresholds_enabled: true\nlocal_read_size_fail_threshold: 64MiB\n' >> "$y";;
    *) log "bad arm $ARM"; return 1;;
  esac
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/yaml.diff"
  echo "label=$L arm=$ARM heap=$HEAP direct=$DIRECT scope=MemorySwapMax=0 start=$(date -u +%FT%TZ) kernel=$(uname -r)" > "$R/run.meta"
  java -version 2>&1 | head -1 >> "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  ( cd "$R" && CASSANDRA_CONF=$R/conf CASSANDRA_LOG_DIR=$R/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT \
    CASSANDRA_HEAPDUMP_DIR=$R \
    JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -Xlog:gc=info,safepoint=info:file=$R/gc.log:time,uptime,level,tags:filecount=20,filesize=20m" \
    setsid nohup systemd-run --user --scope --unit="b17-$L-$(date +%s)" -p MemorySwapMax=0 \
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
  local nm; nm=$(timeout 20 jcmd "$p" VM.native_memory summary 2>/dev/null)
  local oth tot
  oth=$(echo "$nm" | awk '/^-  *Other \(reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  local rss ra; rss=$(awk '/VmRSS/{print $2}' /proc/"$p"/status 2>/dev/null); ra=$(awk '/RssAnon/{print $2}' /proc/"$p"/status 2>/dev/null)
  local cg=/sys/fs/cgroup$(cat "$R/cgroup.path" 2>/dev/null) mc ok
  mc=$(cat "$cg/memory.current" 2>/dev/null); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events" 2>/dev/null)
  [ -f "$cg/memory.events" ] && { rm -f "$R/memory.events.last"; cat "$cg/memory.events" > "$R/memory.events.last"; }
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,nmtOtherKB=${oth:-NA},nmtTotalKB=${tot:-NA},rssKB=${rss:-NA},rssAnonKB=${ra:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" >> "$R/readings.csv"
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
