#!/usr/bin/env bash
# 3-b confirm (2026-11-23): copy of the stage-2 controller; ROOT/SHM moved, auth on in every yaml (mkconf), unit names 3bc10-.
# C10 ring controller (pc91, local): three Cassandra 5.0.9 instances on 127.0.0.1/.2/.3, unmodified build copied from
# /mydata/s4/cassandra-base. Only addresses/ports/directories change (environment), plus arm I / I4 on node 1.
#   arm A : shipped defaults
#   arm I : A + -Dcassandra.max_concurrent_range_requests=1 on node 1 only (intervention)
#   arm I4: A + -Dcassandra.max_concurrent_range_requests=4 on node 1 only (optional)
#   arm LOAD: empty node dirs, all heaps 8G, sequential bootstrap (node 1, then 2, then 3)
#   ring-ctl.sh start <label> <A|I|I4|LOAD> <heap1 e.g. 2G|auto>
#   ring-ctl.sh stop <label> | alive <label> <i> | pid <label> <i> | read <label> <tag> | hist <label> <tag> | drops <label> <tag>
set -uo pipefail
ROOT=/mydata/s4/3b-C10
SHM=/dev/shm/3b-c10
BUILD=$ROOT/tree
NT="$BUILD/bin/nodetool -h 127.0.0.1"
CPUS=(x 0-15 16-23 24-29)
JMX=(x 7199 7299 7399)
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/n$2/logs " | head -1; }
mib(){ local v=$1; case $v in *G) echo $(( ${v%G} * 1024 ));; *M) echo "${v%M}";; esac; }

mkconf(){ # <label> <i>
  local R; R=$(rd "$1"); local i=$2 N=$R/n$2
  mkdir -p "$N/logs"; cp -r "$ROOT/conf-pristine" "$N/conf"
  local y=$N/conf/cassandra.yaml D=$SHM/node$i
  sed -i \
    -e "s|^cluster_name: 'Test Cluster'|cluster_name: 'C10'|" \
    -e "s|^listen_address: localhost|listen_address: 127.0.0.$i|" \
    -e "s|^rpc_address: localhost|rpc_address: 127.0.0.$i|" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $D/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $D/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $D/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $D/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $D/cdc_raw|" \
    -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
    -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
    "$y"
  sed -i -e "s|^JMX_PORT=\"7199\"|JMX_PORT=\"${JMX[$i]}\"|" "$N/conf/cassandra-env.sh"
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$N/yaml.diff"
  diff "$ROOT/conf-pristine/cassandra-env.sh" "$N/conf/cassandra-env.sh" > "$N/env.diff"
}

launch(){ # <label> <i> <heap|auto> <extra opts>
  local R; R=$(rd "$1"); local i=$2 HEAP=$3 EXTRA=$4 N=$R/n$2
  local HM=31744; [ "$HEAP" != auto ] && HM=$(mib "$HEAP")
  local MM=$(( HM + 15872 + 8192 ))
  local HENV=""; [ "$HEAP" != auto ] && HENV=$HEAP
  echo "n$i heap=$HEAP cpus=${CPUS[$i]} jmx=${JMX[$i]} scopeMemoryMax=${MM}M extra=\"$EXTRA\"" >> "$R/run.meta"
  ( cd "$N" && CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=$HENV CASSANDRA_HEAPDUMP_DIR=$N \
    JVM_EXTRA_OPTS="$EXTRA" \
    setsid nohup taskset -c "${CPUS[$i]}" systemd-run --user --scope --unit="3bc10-$1-n$i-$(date +%s)" -p MemoryMax=${MM}M -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$N/stdout.log" 2>&1 & )
  local k p=""; for k in $(seq 1 20); do sleep 1; p=$(pid "$1" "$i"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $1 n$i"; return 1; }
  echo "$p" > "$N/cass.pid"
  sed -n 's/^0:://p' /proc/"$p"/cgroup > "$N/cgroup.path"
  log "started $1 n$i pid $p cpus ${CPUS[$i]} cgroup $(cat "$N/cgroup.path")"
}

waitcql(){ # <label> <i> <secs>
  local R; R=$(rd "$1"); local k
  for k in $(seq 1 $(( $3 / 2 ))); do
    grep -q "Starting listening for CQL clients" "$R/n$2/logs/system.log" 2>/dev/null && { log "CQL up n$2"; return 0; }
    [ "$(alive "$1" "$2")" = DEAD ] && { log "n$2 died during start"; return 1; }
    sleep 2
  done
  log "n$2 CQL not up in $3 s"; return 1
}

waitun(){ # <n> <secs>
  local k
  for k in $(seq 1 $(( $2 / 2 ))); do
    [ "$($NT -p 7199 status 2>/dev/null | grep -c '^UN')" -ge "$1" ] && { log "$1 x UN"; return 0; }
    sleep 2
  done
  log "not $1 x UN in $2 s"; $NT -p 7199 status 2>&1 | tail -6; return 1
}

start(){
  local L=$1 ARM=$2 HEAP1=$3 R; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  rm -rf "$R"; mkdir -p "$R"
  local i
  for i in 1 2 3; do
    rm -rf "$SHM/node$i"
    if [ "$ARM" = LOAD ]; then mkdir -p "$SHM/node$i"/{data,commitlog,hints,saved_caches,cdc_raw}
    else cp -a "$SHM/template$i" "$SHM/node$i" || { log "clone failed n$i"; return 1; }; fi
    mkconf "$L" "$i"
  done
  echo "label=$L arm=$ARM heap1=$HEAP1 start=$(date -u +%FT%TZ)" > "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  local X1="-XX:NativeMemoryTracking=summary -Xlog:gc*=info,safepoint=info:file=$R/n1/gc.log:time,uptime,level,tags:filecount=20,filesize=50m"
  case $ARM in
    A|LOAD) ;;
    I) X1="$X1 -Dcassandra.max_concurrent_range_requests=1";;
    I4) X1="$X1 -Dcassandra.max_concurrent_range_requests=4";;
    *) log "bad arm $ARM"; return 1;;
  esac
  if [ "$ARM" = LOAD ]; then
    launch "$L" 1 8G "$X1" || return 1; waitcql "$L" 1 180 || return 1
    launch "$L" 2 8G "" || return 1; waitcql "$L" 2 300 || return 1; waitun 2 120 || return 1
    launch "$L" 3 8G "" || return 1; waitcql "$L" 3 300 || return 1; waitun 3 120 || return 1
  else
    launch "$L" 1 "$HEAP1" "$X1" || return 1; waitcql "$L" 1 180 || return 1
    launch "$L" 2 8G "" || return 1; launch "$L" 3 8G "" || return 1
    waitcql "$L" 2 180 || return 1; waitcql "$L" 3 180 || return 1; waitun 3 120 || return 1
  fi
  for i in 1 2 3; do
    echo "n$i resolved: $(ps -o args= -p "$(pid "$L" $i)" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|max_concurrent_range|NativeMemory|UseG1|G1HeapRegion' | tr '\n' ' ') nproc=$(taskset -c ${CPUS[$i]} nproc)" >> "$R/run.meta"
  done
  ( setsid nohup taskset -c 30-31 java -Xmx64m -cp "$ROOT/cls" C10Sampler "$R/samples.csv" "$R/sampler.stop" 1000 7199 > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
  log "ring ready $L"
}

read_(){ # node-1 NMT/RSS/scope + last JMX sample
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L" 1)
  local nm; nm=$(timeout 20 jcmd "$p" VM.native_memory summary 2>/dev/null)
  local tot; tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  local ra; ra=$(awk '/RssAnon/{print $2}' /proc/"$p"/status 2>/dev/null)
  local cg=/sys/fs/cgroup$(cat "$R/n1/cgroup.path" 2>/dev/null) mc ok
  mc=$(cat "$cg/memory.current" 2>/dev/null); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events" 2>/dev/null)
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,nmtTotalKB=${tot:-NA},rssAnonKB=${ra:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" | tee -a "$R/readings.csv"
}

events(){ # save scope memory.events for all three (while the scopes exist)
  local R; R=$(rd "$1"); local i
  for i in 1 2 3; do local cg=/sys/fs/cgroup$(cat "$R/n$i/cgroup.path" 2>/dev/null)
    [ -f "$cg/memory.events" ] && { echo "n$i $(tr '\n' ' ' < "$cg/memory.events")"; } ; done > "$R/memory.events.tmp"
  [ -s "$R/memory.events.tmp" ] && mv "$R/memory.events.tmp" "$R/memory.events.last"
}

drops(){ # replica-side outbound drops (nodes 2/3 netstats) + node-1 netstats
  local R; R=$(rd "$1"); local i
  for i in 1 2 3; do echo "== n$i $2"; timeout 30 $NT -p ${JMX[$i]} netstats 2>&1 | sed -n '/Pool Name/,$p'; done >> "$R/netstats.txt"
}

hist(){ timeout 120 jcmd "$(pid "$1" 1)" GC.class_histogram > "$(rd "$1")/histo-$2.txt" 2>&1; log "histogram $1 $2"; }

stop(){
  local L=$1 R i p sp; R=$(rd "$L"); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2; [ -n "$sp" ] && kill "$sp" 2>/dev/null
  events "$L"
  for i in 1 2 3; do
    p=$(pid "$L" $i)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      timeout 120 $NT -p ${JMX[$i]} drain > "$R/n$i/drain.out" 2>&1
      kill "$p"; for k in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
      kill -0 "$p" 2>/dev/null && kill -9 "$p"
    fi
  done
  log "stopped $L"
}

alive(){ local p; p=$(cat "$(rd "$1")/n$2/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

cmd=$1; shift
case $cmd in
  start) start "$@";; stop) stop "$@";; alive) alive "$@";; pid) pid "$@";; read) read_ "$@";;
  hist) hist "$@";; drops) drops "$@";; events) events "$@";; waitun) waitun "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
