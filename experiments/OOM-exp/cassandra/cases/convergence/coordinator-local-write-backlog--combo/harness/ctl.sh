#!/usr/bin/env bash
# S2 per-node Cassandra controller (runs ON the node). Roles:
#   V  apt140 10.10.1.1 dc=c  victim coordinator + replica, build ~/cassandra-b1, dirs /mydata/s2/V
#   R  apt149 10.10.1.5 dc=r  slow replica, build ~/cassandra-c1, data/commitlog/hints on dm-delay /mydata/s2/slow
# Only environment settings are changed; every capacity, timeout, cache, hints setting stays at the shipped default.
#   ctl.sh gen <V|R> <xmx> [key=value ...] | start <V|R> | stop <V|R> | pid <V|R>
set -uo pipefail
declare -A IP=([V]=10.10.1.1 [R]=10.10.1.5) DC=([V]=c [R]=r)
declare -A TOK=([V]=-9223372036854775808 [R]=0)
declare -A BLD=([V]=$HOME/cassandra-b1 [R]=$HOME/cassandra-c1)
ROOT=/mydata/s2/inst
log(){ echo "[$(date '+%T')] $*"; }
gen(){
  local n=$1 xmx=$2; shift 2; local d=$ROOT/$n dd=$ROOT/$n b=${BLD[$n]} ip=${IP[$n]}
  [ "$n" = R ] && dd=/mydata/s2/slow/R
  rm -rf "$d" "$dd"; mkdir -p "$d"/{logs,dumps} "$dd"/{data,commitlog,hints,saved_caches}
  cp -r "$b/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 's2ring'/" -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"10.10.1.1:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $dd/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $dd/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $dd/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $dd/saved_caches|" "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  local kv k; for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  printf 'dc=%s\nrack=r1\n' "${DC[$n]}" > "$d/conf/cassandra-rackdc.properties"
  echo "$xmx" > "$d/xmx"; diff "$b/conf/cassandra.yaml" "$y" > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" || { log "GEN FAIL $n"; return 1; }; log "gen $n xmx=$xmx extra=[$*]"
}
start(){
  local n=$1 d=$ROOT/$1 b=${BLD[$1]}
  ( ulimit -n 100000; cd "$b"; CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
    MAX_HEAP_SIZE="$(cat $d/xmx)" HEAP_NEWSIZE="256M" "$b/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  log "launched $n pid=$(cat $d/cass.pid 2>/dev/null)"
}
stop(){
  local p; p=$(cat $ROOT/$1/cass.pid 2>/dev/null); [ -n "$p" ] || return 0
  kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; log "stopped $1 ($p)"
}
case "${1:-}" in gen) shift; gen "$@";; start) start "$2";; stop) stop "$2";; pid) cat $ROOT/$2/cass.pid;; *) exit 2;; esac
