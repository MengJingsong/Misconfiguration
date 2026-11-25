#!/usr/bin/env bash
# 3-b confirm R24 (pc72, 2026-11-24): stage 2's ctl.sh with ROOT=/mydata/s4/3b-R24 and conf-auth (shipped conf + PasswordAuthenticator/CassandraAuthorizer).
# Origin: R24 two-instance controller on pc82 (stage 2, 2026-11-24), adapted from B22's ctl.sh (OOM-exp B22), itself from U4's victim-ctl.sh and stage 4's RFP cluster-run.sh.
# Unmodified 5.0.9 build copied from /mydata/s4/cassandra-base. Node 1 = victim/coordinator 127.0.0.1 (JMX 7199),
# node 2 = peer replica 127.0.0.2 (JMX 7299, heap 16G). Only directories, addresses, cluster_name, auto_bootstrap change.
#   ctl.sh prep  <label> <LOAD|CLONE>        LOAD: empty node dirs; CLONE: fresh cp -a of $ROOT/template-n1|n2
#   ctl.sh start <label> <1|2> <heap> <direct|auto> [diag]   (each node in its own systemd scope, MemorySwapMax=0)
#   ctl.sh ready <label> <1|2>               wait for "Starting listening for CQL clients"; record JVM flags
#   ctl.sh ring  <label>                     wait for 2 UN in node 1's view
#   ctl.sh sampler <label>                   start R24Sampler (1 s) on node 1's JMX (env WT/ST = the tables sampled)
#   ctl.sh read <label> <tag> | hist <label> <tag> | rfpk <label> <tag> | stop <label> | alive <label> <i> | pid <label> <i>
set -uo pipefail
ROOT=/mydata/s4/3b-R24
H=$ROOT/harness
BUILD=${BUILD_DIR:-$ROOT/tree}   # R24: BUILD_DIR=$ROOT/tree-patched for the I-patch arm (diagnostic build)
J=$ROOT/tree/build/lib/jars
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/n$2/logs " | head -1; }
jport(){ [ "$1" = 1 ] && echo 7199 || echo 7299; }
NT(){ "$BUILD/bin/nodetool" -h 127.0.0.1 -p "$(jport "$1")" "${@:2}"; }

prep(){
  local L=$1 MODE=$2 R i; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  rm -rf "$ROOT/n1" "$ROOT/n2" "$R"; mkdir -p "$R"
  for i in 1 2; do
    mkdir -p "$R/n$i/logs"
    if [ "$MODE" = LOAD ]; then mkdir -p "$ROOT/n$i"/{data,commitlog,hints,saved_caches,cdc_raw}
    else cp -a "$ROOT/template-n$i" "$ROOT/n$i" || { log "clone n$i failed"; return 1; }; fi
    cp -r "$ROOT/${CONF:-conf-auth}" "$R/n$i/conf"   # CONF=conf-pristine: auth-off diagnostic only
    local y=$R/n$i/conf/cassandra.yaml ip=127.0.0.$i
    sed -i \
      -e "s|^cluster_name: 'Test Cluster'|cluster_name: 'r24'|" \
      -e "s|^listen_address: localhost|listen_address: $ip|" \
      -e "s|^rpc_address: localhost|rpc_address: $ip|" \
      -e "s|^# data_file_directories:|data_file_directories:|" \
      -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/n$i/data|" \
      -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/n$i/commitlog|" \
      -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/n$i/hints|" \
      -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/n$i/saved_caches|" \
      -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/n$i/cdc_raw|" \
      "$y"
    printf '# R24 topology (environment): empty ring, schema created after both are up\nauto_bootstrap: false\n' >> "$y"
    [ "$i" = 2 ] && sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' "$R/n$i/conf/cassandra-env.sh"
    diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$R/n$i/yaml.diff"
    diff "$ROOT/conf-pristine/cassandra-env.sh" "$R/n$i/conf/cassandra-env.sh" > "$R/n$i/env.diff"
  done
  du -sh "$ROOT/n1" "$ROOT/n2" | tr '\n' ' '; echo
}

start(){
  local L=$1 i=$2 HEAP=$3 DIRECT=${4:-auto} DIAG=${5:-} R; R=$(rd "$L")
  local DENV=""; [ "$DIRECT" != auto ] && DENV=$DIRECT
  local EXTRA="-XX:NativeMemoryTracking=summary"
  [ "$DIAG" = diag ] && EXTRA="$EXTRA -javaagent:$J/byteman-4.0.20.jar=script:$H/rfp.btm,sys:$ROOT/cls/rfp-helper.jar -Drfp.out=$R/probe.txt"
  echo "label=$L node=$i heap=$HEAP direct=$DIRECT diag=${DIAG:-no} start=$(date -u +%FT%TZ)" >> "$R/run.meta"
  ( cd "$R/n$i" && CASSANDRA_CONF=$R/n$i/conf CASSANDRA_LOG_DIR=$R/n$i/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DENV \
    CASSANDRA_HEAPDUMP_DIR=$R/n$i JVM_EXTRA_OPTS="$EXTRA" \
    setsid nohup systemd-run --user --scope --unit="3br24-$L-n$i-$(date +%s)" -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$R/n$i/stdout.log" 2>&1 & )
  local k p=""; for k in $(seq 1 20); do sleep 1; p=$(pid "$L" "$i"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $L n$i"; return 1; }
  echo "$p" > "$R/n$i/cass.pid"
  sed -n 's/^0:://p' /proc/"$p"/cgroup > "$R/n$i/cgroup.path"
  log "started $L n$i pid $p cgroup $(cat "$R/n$i/cgroup.path")"
}

ready(){
  local L=$1 i=$2 k R; R=$(rd "$L")
  for k in $(seq 1 90); do
    if grep -q "Starting listening for CQL clients" "$R/n$i/logs/system.log" 2>/dev/null; then
      log "ready $L n$i"
      echo -n "n$i flags: " >> "$R/run.meta"
      ps -o args= -p "$(pid "$L" "$i")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause|javaagent' | tr '\n' ' ' | tee -a "$R/run.meta"; echo | tee -a "$R/run.meta"
      return 0
    fi
    [ "$(alive "$L" "$i")" = DEAD ] && { log "n$i died during start"; tail -5 "$R/n$i/logs/system.log"; return 1; }
    sleep 2
  done
  log "n$i not ready in 180 s"; return 1
}

ring(){
  local L=$1 k s
  for k in $(seq 1 60); do
    s=$(NT 1 status 2>/dev/null)
    if [ "$(echo "$s" | grep -c '^UN')" = 2 ]; then log "ring: 2 UN in node 1's view"; echo "$s" > "$(rd "$L")/ring.txt"; return 0; fi
    sleep 2
  done
  log "ring not 2 UN after 120 s"; NT 1 status; return 1
}

sampler(){
  local L=$1 R; R=$(rd "$L")
  ( setsid nohup java -Xmx64m -cp "$ROOT/cls" R24Sampler "$R/samples.csv" "$R/sampler.stop" 1000 7199 ${WT:-w4k} ${ST:-s4k} > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
}

read_(){
  local L=$1 T=$2 R p; R=$(rd "$L"); p=$(pid "$L" 1)
  local nm oth tot; nm=$(timeout 20 jcmd "$p" VM.native_memory summary 2>/dev/null)
  oth=$(echo "$nm" | awk '/^-  *Other \(reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  tot=$(echo "$nm" | awk '/^Total: reserved=/{gsub(/[^0-9 ]/," ",$0); split($0,a," "); print a[2]; exit}')
  local ra; ra=$(awk '/RssAnon/{print $2}' /proc/"$p"/status 2>/dev/null)
  local cg=/sys/fs/cgroup$(cat "$R/n1/cgroup.path" 2>/dev/null) mc ok
  mc=$(cat "$cg/memory.current" 2>/dev/null); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events" 2>/dev/null)
  [ -f "$cg/memory.events" ] && cat "$cg/memory.events" > "$R/memory.events.last"
  local last; last=$(grep -v ERR "$R/samples.csv" 2>/dev/null | tail -1)
  echo "$(date -u +%s),$T,nmtOtherKB=${oth:-NA},nmtTotalKB=${tot:-NA},rssAnonKB=${ra:-NA},scopeCurB=${mc:-NA},scopeOomKill=${ok:-NA},$last" | tee -a "$R/readings.csv"
}

gc(){ timeout 60 jcmd "$(pid "$1" 1)" GC.run > /dev/null 2>&1; log "GC.run $1 n1"; }
hist(){ timeout 120 jcmd "$(pid "$1" 1)" GC.class_histogram > "$(rd "$1")/histo-$2.txt" 2>&1; log "histogram $1 $2"; }
rfpk(){ local R; R=$(rd "$1"); for t in ${TABLES:-w2k w4k w8k w12k s2k s4k s8k s12k}; do echo "$2 $t $(timeout 20 java -cp "$ROOT/cls" RfpJmx 127.0.0.1:7199 hist r24 $t 2>&1)"; done | tee -a "$R/rfpk.txt"
        echo "$2 thresholds $(timeout 20 java -cp "$ROOT/cls" RfpJmx 127.0.0.1:7199 get 2>&1)" | tee -a "$R/rfpk.txt"; }

stopn(){ # $1 label $2 node
  local L=$1 i=$2 R p; R=$(rd "$L"); p=$(cat "$R/n$i/cass.pid" 2>/dev/null)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    timeout 120 "$BUILD/bin/nodetool" -h 127.0.0.1 -p "$(jport "$i")" drain > "$R/n$i/drain.out" 2>&1
    kill "$p"; local k; for k in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L n$i"
}
stop(){
  local L=$1 R sp; R=$(rd "$L"); sp=$(cat "$R/sampler.pid" 2>/dev/null)
  touch "$R/sampler.stop"; sleep 2; [ -n "$sp" ] && kill "$sp" 2>/dev/null
  stopn "$L" 1; stopn "$L" 2
}

alive(){ local p; p=$(cat "$(rd "$1")/n$2/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

cmd=$1; shift
case $cmd in
  prep) prep "$@";; start) start "$@";; ready) ready "$@";; ring) ring "$@";; sampler) sampler "$@";;
  read) read_ "$@";; gc) gc "$@";; hist) hist "$@";; rfpk) rfpk "$@";; stop) stop "$@";; stopn) stopn "$@";;
  alive) alive "$@";; pid) pid "$@";; nt) NT "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
