#!/usr/bin/env bash
# B6 run-4 single-host ring controller (pc96 / node0, loopback addresses).
#   V1 127.0.0.11 dc=v  slow replica, token MIN  -> owns half of dc v's ranges
#   V2 127.0.0.17 dc=v  slow replica, token 1    -> owns the other half (distinct mutations from V1)
#      V1 and V2 keep data/commitlog/hints on the dm-delay disk /mydata/b6/slow (stall: harness-run2/slowdisk.sh)
#   F  127.0.0.12 dc=f  fast replica (acks CL=ONE)
#   S  127.0.0.13 dc=c  measured coordinator (owns no replica; the client talks only to S)
# No Byteman; default concurrent_writes and timeouts unless passed as key=value.
# Usage:
#   ctl.sh gen <V1|V2|F|S> <xmx> [key=value ...]
#   ctl.sh start <n> | stop <n|all> | status | pid <n>
# BUILD=<dir> overrides the Cassandra build (diagnostic patch build).
set -uo pipefail
BUILD=${BUILD:-/mydata/b6/cassandra}
ROOT=/mydata/b6/ring4
declare -A IP=([V1]=127.0.0.11 [V2]=127.0.0.17 [F]=127.0.0.12 [S]=127.0.0.13)
declare -A DC=([V1]=v [V2]=v [F]=f [S]=c)
declare -A JMX=([V1]=7211 [V2]=7217 [F]=7212 [S]=7213)
declare -A TOK=([V1]=-9223372036854775808 [V2]=1 [F]=-6148914691236517206 [S]=-3074457345618258604)
ALL="V1 V2 F S"
log(){ echo "[$(date '+%T')] $*"; }

gen(){
  local n=$1 xmx=$2; shift 2
  local d=$ROOT/$n ip=${IP[$n]} dd=$ROOT/$n
  case $n in V1|V2) dd=/mydata/b6/slow/$n ;; esac
  rm -rf "$d" "$dd"; mkdir -p "$d"/{logs,dumps} "$dd"/{data,commitlog,hints,saved_caches}
  cp -r "$BUILD/conf" "$d/conf"
  local y=$d/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'b6ring4'/" \
    -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" \
    -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"127.0.0.11:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $dd/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $dd/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $dd/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $dd/saved_caches|" \
    -e "s|^key_cache_size:|key_cache_size: 0MiB|" \
    -e "s|^counter_cache_size:|counter_cache_size: 0MiB|" \
    -e "s|^hinted_handoff_enabled: true|hinted_handoff_enabled: false|" \
    "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  local kv k
  for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  printf 'dc=%s\nrack=r1\n' "${DC[$n]}" > "$d/conf/cassandra-rackdc.properties"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"${JMX[$n]}\"/" "$d/conf/cassandra-env.sh"
  echo "$xmx" > "$d/xmx"; echo "$BUILD" > "$d/build"
  grep -q "^listen_address: $ip" "$y" && grep -q "^hinted_handoff_enabled: false" "$y" \
    && grep -q "^JMX_PORT=\"${JMX[$n]}\"" "$d/conf/cassandra-env.sh" || { log "GEN FAIL $n"; return 1; }
  log "gen $n ip=$ip dc=${DC[$n]} xmx=$xmx build=$BUILD extra=[$*]"
}

start(){
  local n=$1 d=$ROOT/$1 xmx extra="" b
  [ "${HEAPDUMP:-1}" = 0 ] && extra="-XX:-HeapDumpOnOutOfMemoryError"
  xmx=$(cat "$d/xmx"); b=$(cat "$d/build")
  ( ulimit -n 100000
    cd "$b"
    CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
    MAX_HEAP_SIZE="$xmx" HEAP_NEWSIZE="256M" JVM_EXTRA_OPTS="$extra" \
      "$b/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  log "launched $n pid=$(cat "$d/cass.pid" 2>/dev/null) xmx=$xmx"
}

pidof_n(){ cat "$ROOT/$1/cass.pid" 2>/dev/null; }
alive(){ local p; p=$(pidof_n "$1"); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

stop(){
  local n p
  for n in "$@"; do
    p=$(pidof_n "$n"); [ -n "$p" ] || continue
    kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -9 "$p" 2>/dev/null; log "stopped $n ($p)"
  done
}

case "${1:-}" in
  gen) shift; gen "$@" ;;
  start) start "$2" ;;
  stop) if [ "$2" = all ]; then stop S F V2 V1; else stop "$2"; fi ;;
  status) for n in $ALL; do if alive $n; then echo "$n UP pid=$(pidof_n $n)"; else echo "$n DOWN"; fi; done ;;
  pid) pidof_n "$2" ;;
  *) echo "usage: $0 gen|start|stop|status|pid" >&2; exit 2 ;;
esac
