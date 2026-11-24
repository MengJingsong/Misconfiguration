#!/usr/bin/env bash
# 3-b confirm S2 (pc91, 2026-11-23): ring controller for condition G1 on ONE host. Three Cassandra 5.0.9 instances
# (copy of /mydata/s4/cassandra-base, unmodified) on 127.0.0.1 (n1 = V, the attacked coordinator, seed),
# 127.0.0.2 (n2 = R1), 127.0.0.3 (n3 = R2). Same yaml changes as run 2's ctl.sh (cluster name, num_tokens 1 +
# initial_token, listen/rpc address, seed, GossipingPropertyFileSnitch dc=c rack=r1, directories,
# auto_bootstrap false) plus the security settings of the 3-b threat model:
#   authenticator: PasswordAuthenticator, authorizer: CassandraAuthorizer, role_manager: CassandraRoleManager
#   (shipped), network_authorizer: AllowAllNetworkAuthorizer (shipped).
# Every capacity constraint stays at its shipped default. Heap 2G on all three (V7 as G1), HEAP_NEWSIZE 256M (as run
# 2, ignored by G1), direct memory auto, no container limit. Each instance pinned to 4 physical cores (8 hardware
# threads), standing in for run 2's 8-core m400 nodes; client, victim and samplers on the remaining 8 threads.
# No systemd scope (pc91 has no linger): plain setsid/nohup; swap is watched through VmSwap in the sampler.
#   ring-ctl.sh start <label> | stop <label> | alive <label> <i> | pid <label> <i>
set -uo pipefail
ROOT=/mydata/s4/3b-S2
BUILD=$ROOT/tree
NT="$BUILD/bin/nodetool -h 127.0.0.1"
CPUS=(x "0,2,4,6,16,18,20,22" "8,10,12,14,24,26,28,30" "1,3,5,7,17,19,21,23")
JMX=(x 7199 7299 7399)
TOK=(x -9223372036854775808 -3074457345618258603 3074457345618258602)
HEAP=${HEAP:-2G}
log(){ echo "[$(TZ=America/New_York date '+%F %T %Z')] $*"; }
rd(){ echo "$ROOT/runs/$1"; }
dd_(){ echo "$ROOT/data/$1"; }
pid(){ pgrep -f "Dcassandra.logdir=$(rd "$1")/n$2/logs " | head -1; }

mkconf(){ # <label> <i>
  local R; R=$(rd "$1"); local i=$2 N=$R/n$2 D; D=$(dd_ "$1")/node$2
  mkdir -p "$N/logs" "$D"/{data,commitlog,hints,saved_caches,cdc_raw}; cp -r "$ROOT/conf-pristine" "$N/conf"
  local y=$N/conf/cassandra.yaml
  sed -i \
    -e "s|^cluster_name: 'Test Cluster'|cluster_name: 's2r3b'|" \
    -e "s|^num_tokens: 16|num_tokens: 1|" \
    -e "s|^listen_address: localhost|listen_address: 127.0.0.$i|" \
    -e "s|^rpc_address: localhost|rpc_address: 127.0.0.$i|" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"127.0.0.1:7000\"|" \
    -e "s|^endpoint_snitch: SimpleSnitch|endpoint_snitch: GossipingPropertyFileSnitch|" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $D/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $D/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $D/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $D/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $D/cdc_raw|" \
    -e "s|^authenticator: AllowAllAuthenticator|authenticator: PasswordAuthenticator|" \
    -e "s|^authorizer: AllowAllAuthorizer|authorizer: CassandraAuthorizer|" \
    "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$i]}"; } >> "$y"
  printf 'dc=c\nrack=r1\n' > "$N/conf/cassandra-rackdc.properties"
  sed -i -e "s|^JMX_PORT=\"7199\"|JMX_PORT=\"${JMX[$i]}\"|" "$N/conf/cassandra-env.sh"
  diff "$ROOT/conf-pristine/cassandra.yaml" "$y" > "$N/yaml.diff"
  diff "$ROOT/conf-pristine/cassandra-env.sh" "$N/conf/cassandra-env.sh" > "$N/env.diff"
  grep -q "^listen_address: 127.0.0.$i" "$y" && grep -q "^authenticator: PasswordAuthenticator" "$y" && grep -q "^authorizer: CassandraAuthorizer" "$y" \
    || { log "GEN FAIL n$i"; return 1; }
}

launch(){ # <label> <i>
  local R; R=$(rd "$1"); local i=$2 N=$R/n$2
  echo "n$i heap=$HEAP cpus=${CPUS[$i]} jmx=${JMX[$i]} token=${TOK[$i]}" >> "$R/run.meta"
  ( cd "$N" && ulimit -n 100000 && CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=$HEAP HEAP_NEWSIZE=256M \
    CASSANDRA_HEAPDUMP_DIR=$N setsid nohup taskset -c "${CPUS[$i]}" "$BUILD/bin/cassandra" -f < /dev/null > "$N/stdout.log" 2>&1 & )
  local k p=""; for k in $(seq 1 20); do sleep 1; p=$(pid "$1" "$i"); [ -n "$p" ] && break; done
  [ -z "$p" ] && { log "no java pid for $1 n$i"; return 1; }
  echo "$p" > "$N/cass.pid"; log "started $1 n$i pid $p cpus ${CPUS[$i]}"
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
  local L=$1 R; R=$(rd "$L")
  if pgrep -f 'java.*CassandraDaemon' >/dev/null; then log "REFUSE: a CassandraDaemon is already running"; pgrep -af 'java.*CassandraDaemon' | cut -c1-150; return 1; fi
  rm -rf "$R" "$(dd_ "$L")"; mkdir -p "$R"
  local i; for i in 1 2 3; do mkconf "$L" "$i" || return 1; done
  echo "label=$L heap=$HEAP start=$(date -u +%FT%TZ)" > "$R/run.meta"
  sha256sum "$BUILD"/build/apache-cassandra-*.jar >> "$R/run.meta" 2>&1
  launch "$L" 1 || return 1; waitcql "$L" 1 240 || return 1
  launch "$L" 2 || return 1; launch "$L" 3 || return 1
  waitcql "$L" 2 240 || return 1; waitcql "$L" 3 240 || return 1; waitun 3 180 || return 1
  for i in 1 2 3; do
    echo "n$i resolved: $(ps -o args= -p "$(pid "$L" $i)" | tr ' ' '\n' | grep -E '^-Xm[sx]|MaxDirect|UseG1|HeapDumpPath|OnOutOfMemory|^-Xlog' | tr '\n' ' ') nproc=$(taskset -c ${CPUS[$i]} nproc)" >> "$R/run.meta"
  done
  $NT -p 7199 status > "$R/status.txt" 2>&1
  log "ring ready $L"
}

stop(){
  local L=$1 R i p; R=$(rd "$L")
  for i in 1 2 3; do
    p=$(pid "$L" $i)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
      kill "$p"; for k in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
      kill -0 "$p" 2>/dev/null && kill -9 "$p"
      log "stopped n$i ($p)"
    fi
  done
}

alive(){ local p; p=$(cat "$(rd "$1")/n$2/cass.pid" 2>/dev/null); if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo ALIVE; else echo DEAD; fi; }

cmd=$1; shift
case $cmd in
  start) start "$@";; stop) stop "$@";; alive) alive "$@";; pid) pid "$@";; waitun) waitun "$@";;
  *) echo "unknown $cmd"; exit 2;;
esac
