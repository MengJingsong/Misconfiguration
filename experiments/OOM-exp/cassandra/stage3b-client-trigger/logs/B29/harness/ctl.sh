#!/usr/bin/env bash
# 3-b confirm B29 (pc82, 2026-11-24): two-instance controller, adapted from the case's stage-2 ctl.sh (harness/ in the case folder).
# One continuous cluster (no templates): node data in $ROOT/n1, $ROOT/n2; each node lifetime logs to $ROOT/runs/<label>/n<i>/.
# Node 1 = 127.0.0.1 (JMX 7199), the replica that is down during the attacker's writes and the attacked coordinator;
# node 2 = 127.0.0.2 (JMX 7299). yaml changes from the shipped conf: directories, addresses, cluster_name, auto_bootstrap
# (as stage 2) plus the two security settings: authenticator PasswordAuthenticator, authorizer CassandraAuthorizer.
#   ctl.sh conf                         make $ROOT/conf-n1, conf-n2 (once)
#   ctl.sh start <label> <i> <heap>     start node i (direct auto, NMT summary as stage 2), own systemd scope, MemorySwapMax=0
#   ctl.sh ready <label> <i> | ring | sampler <label> | stopn <label> <i> [nodrain] | alive <label> <i> | nt <i> <args...>
set -uo pipefail
ROOT=/mydata/s4/3b-B29
BUILD=$ROOT/tree
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/n$2/logs " | head -1; }
jport(){ [ "$1" = 1 ] && echo 7199 || echo 7299; }
NT(){ "$BUILD/bin/nodetool" -h 127.0.0.1 -p "$(jport "$1")" "${@:2}" 2>&1 | grep -v 'picked up\|^$' ; }

conf(){
  local i
  for i in 1 2; do
    local C=$ROOT/conf-n$i ip=127.0.0.$i; rm -rf "$C"; cp -r "$ROOT/conf-pristine" "$C"
    mkdir -p "$ROOT/n$i"/{data,commitlog,hints,saved_caches,cdc_raw}
    local y=$C/cassandra.yaml
    sed -i \
      -e "s|^cluster_name: 'Test Cluster'|cluster_name: 'b29'|" \
      -e "s|^listen_address: localhost|listen_address: $ip|" \
      -e "s|^rpc_address: localhost|rpc_address: $ip|" \
      -e "s|^# data_file_directories:|data_file_directories:|" \
      -e "s|^#     - /var/lib/cassandra/data|    - $ROOT/n$i/data|" \
      -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $ROOT/n$i/commitlog|" \
      -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $ROOT/n$i/hints|" \
      -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $ROOT/n$i/saved_caches|" \
      -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $ROOT/n$i/cdc_raw|" \
      -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
      -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
      "$y"
    printf '# B29 topology (environment): empty ring, schema created after both are up\nauto_bootstrap: false\n' >> "$y"
    [ "$i" = 2 ] && sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' "$C/cassandra-env.sh"
    diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$ROOT/yaml-n$i.diff"
    diff "$ROOT/conf-pristine/cassandra-env.sh" "$C/cassandra-env.sh" > "$ROOT/env-n$i.diff"
  done
  log "conf made"
}

start(){
  local L=$1 i=$2 HEAP=$3 R; R=$(rd "$L")
  if [ -n "$(pgrep -f "Dcassandra.logdir=$ROOT/runs/[^ ]*/n$i/logs ")" ]; then log "REFUSE: node $i already running"; return 1; fi
  mkdir -p "$R/n$i/logs"
  echo "label=$L node=$i heap=$HEAP start=$(date -u +%FT%TZ)" >> "$R/run.meta"
  ( cd "$R/n$i" && CASSANDRA_CONF=$ROOT/conf-n$i CASSANDRA_LOG_DIR=$R/n$i/logs MAX_HEAP_SIZE=$HEAP \
    CASSANDRA_HEAPDUMP_DIR=$R/n$i JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary" \
    setsid nohup systemd-run --user --scope --unit="3bb29-$L-n$i-$(date +%s)" -p MemorySwapMax=0 \
      "$BUILD/bin/cassandra" -f < /dev/null > "$R/n$i/stdout.log" 2>&1 & )
  local k p=""; for k in $(seq 1 20); do sleep 1; p=$(pid "$L" "$i"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $L n$i"; return 1; }
  echo "$p" > "$R/n$i/cass.pid"
  sed -n 's/^0:://p' /proc/"$p"/cgroup > "$R/n$i/cgroup.path"
  log "started $L n$i pid $p heap $HEAP"
}

ready(){
  local L=$1 i=$2 k R; R=$(rd "$L")
  for k in $(seq 1 150); do
    if grep -q "Starting listening for CQL clients" "$R/n$i/logs/system.log" 2>/dev/null; then
      log "ready $L n$i"
      echo -n "n$i flags: " >> "$R/run.meta"
      ps -o args= -p "$(pid "$L" "$i")" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|NativeMemory|HeapDump|OnOutOfMemory|UseG1|G1HeapRegion|MaxGCPause' | tr '\n' ' ' >> "$R/run.meta"; echo >> "$R/run.meta"
      return 0
    fi
    [ "$(alive "$L" "$i")" = DEAD ] && { log "n$i died during start"; tail -5 "$R/n$i/logs/system.log"; return 1; }
    sleep 2
  done
  log "n$i not ready in 300 s"; return 1
}

ring(){ # $1 node whose view, $2 expected UN count
  local v=${1:-1} n=${2:-2} k s
  for k in $(seq 1 60); do
    s=$(NT "$v" status 2>/dev/null)
    if [ "$(echo "$s" | grep -c '^UN')" = "$n" ]; then log "ring: $n UN in node $v's view"; echo "$s" | grep -E '^(UN|DN|UJ|DL)'; return 0; fi
    sleep 2
  done
  log "ring not $n UN after 120 s"; NT "$v" status; return 1
}

sampler(){
  local L=$1 R; R=$(rd "$L")
  ( setsid nohup java -Xmx64m -cp "$ROOT/cls" B29Sampler "$R/samples.csv" "$R/sampler.stop" 1000 7199 > "$R/sampler.out" 2>&1 < /dev/null & echo $! > "$R/sampler.pid" )
}
samplerstop(){ local R; R=$(rd "$1"); touch "$R/sampler.stop"; sleep 2; kill "$(cat "$R/sampler.pid" 2>/dev/null)" 2>/dev/null; true; }

stopn(){ # $1 label $2 node [$3 nodrain]
  local L=$1 i=$2 R p; R=$(rd "$L"); p=$(cat "$R/n$i/cass.pid" 2>/dev/null)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    [ "${3:-}" = nodrain ] || timeout 180 "$BUILD/bin/nodetool" -h 127.0.0.1 -p "$(jport "$i")" drain > "$R/n$i/drain.out" 2>&1
    kill "$p"; local k; for k in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -0 "$p" 2>/dev/null && kill -9 "$p"
  fi
  log "stopped $L n$i"
}

alive(){ local p; p=$(cat "$(rd "$1")/n$2/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

cmd=$1; shift
case $cmd in
  conf) conf;; start) start "$@";; ready) ready "$@";; ring) ring "$@";; sampler) sampler "$@";; samplerstop) samplerstop "$@";;
  stopn) stopn "$@";; alive) alive "$@";; pid) pid "$@";; nt) NT "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
