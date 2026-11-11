#!/usr/bin/env bash
# B6 single-host 3-instance ring controller (node0, loopback addresses).
#   V 127.0.0.11 dc=v  slow replica (Byteman delay, concurrent_writes=2)
#   F 127.0.0.12 dc=f  fast replica
#   S 127.0.0.13 dc=c  measured coordinator (owns no replica)
# Usage:
#   ctl.sh gen <V|F|S> <xmx> [key=value ...]   # extra yaml keys appended (e.g. write_request_timeout=60000ms)
#   ctl.sh start <V|F|S> | stop <V|F|S|all> | status | pid <V|F|S>
set -uo pipefail
BUILD=/mydata/b6/cassandra
ROOT=/mydata/b6/ring
HERE=$(cd "$(dirname "$0")" && pwd)
declare -A IP=([V]=127.0.0.11 [F]=127.0.0.12 [S]=127.0.0.13)
declare -A DC=([V]=v [F]=f [S]=c)
declare -A JMX=([V]=7211 [F]=7212 [S]=7213)
declare -A TOK=([V]=-9223372036854775808 [F]=-3074457345618258603 [S]=3074457345618258602)
log(){ echo "[$(date '+%T')] $*"; }

gen(){
  local n=$1 xmx=$2; shift 2
  local d=$ROOT/$n ip=${IP[$n]}
  rm -rf "$d"; mkdir -p "$d"/{data,commitlog,hints,saved_caches,logs,dumps}
  cp -r "$BUILD/conf" "$d/conf"
  local y=$d/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'b6ring'/" \
    -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" \
    -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"127.0.0.11:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" \
    -e "s|^key_cache_size:|key_cache_size: 0MiB|" \
    -e "s|^counter_cache_size:|counter_cache_size: 0MiB|" \
    -e "s|^hinted_handoff_enabled: true|hinted_handoff_enabled: false|" \
    "$y"
  if [ "$n" = V ]; then sed -i "s/^concurrent_writes: 32/concurrent_writes: 2/" "$y"; fi
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  local kv k
  for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  printf 'dc=%s\nrack=r1\n' "${DC[$n]}" > "$d/conf/cassandra-rackdc.properties"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"${JMX[$n]}\"/" "$d/conf/cassandra-env.sh"
  echo "$xmx" > "$d/xmx"
  grep -q "^listen_address: $ip" "$y" && grep -q "^hinted_handoff_enabled: false" "$y" \
    && grep -q "^JMX_PORT=\"${JMX[$n]}\"" "$d/conf/cassandra-env.sh" || { log "GEN FAIL $n"; return 1; }
  log "gen $n ip=$ip dc=${DC[$n]} xmx=$xmx extra=[$*]"
}

start(){
  local n=$1 d=$ROOT/$1 xmx extra=""
  [ "${HEAPDUMP:-1}" = 0 ] && extra="-XX:-HeapDumpOnOutOfMemoryError"
  xmx=$(cat "$d/xmx")
  if [ "$n" = V ]; then
    local bm=$BUILD/build/lib/jars/byteman-4.0.20.jar
    extra="$extra -javaagent:$bm=boot:$bm,script:$HERE/mutation-delay.btm,listener:true"
  fi
  ( ulimit -n 100000
    cd "$BUILD"
    CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
    MAX_HEAP_SIZE="$xmx" HEAP_NEWSIZE="256M" JVM_EXTRA_OPTS="$extra" \
      "$BUILD/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
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
  stop) if [ "$2" = all ]; then stop S F V; else stop "$2"; fi ;;
  status) for n in V F S; do if alive $n; then echo "$n UP pid=$(pidof_n $n)"; else echo "$n DOWN"; fi; done ;;
  pid) pidof_n "$2" ;;
  *) echo "usage: $0 gen|start|stop|status|pid" >&2; exit 2 ;;
esac
