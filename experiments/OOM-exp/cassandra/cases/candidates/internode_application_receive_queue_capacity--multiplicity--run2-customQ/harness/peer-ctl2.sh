#!/usr/bin/env bash
# C1-reopen peer-host controller. Coordinator instances, datacenter=c, own NO replica
# (keyspace is NTS {v:1} -> replica only on the victim). GossipingPropertyFileSnitch,
# explicit initial_token per instance, small heap. Distinct LAN IP alias + JMX port.
#   peer-ctl2.sh aliasup <aliasCSV> | aliasdown <aliasCSV>
#   peer-ctl2.sh gen <aliasCSV> | start <aliasCSV> | status | stop
set -uo pipefail
BUILD=$HOME/cassandra-c1
ROOT=/mydata/c1r
IFACE=enp8s0d1
SEEDS='10.10.1.1:7000,10.10.1.32:7000'
XMX=${XMX:-1G}
log(){ echo "[$(date '+%T')] $*"; }
jmxport(){ echo $((17000 + ${1##*.})); }
# evenly-spaced tokens (9-node ring, victim=idx0). coordinator ip -> token:
declare -A TOK=(
 [10.10.1.32]=-7173733806442603407 [10.10.1.33]=-5124095576030431006
 [10.10.1.48]=-3074457345618258605 [10.10.1.49]=-1024819115206086204
 [10.10.1.64]=1024819115206086197  [10.10.1.65]=3074457345618258598
 [10.10.1.80]=5124095576030430999  [10.10.1.81]=7173733806442603400 )

gen_one(){
  local ip=$1 d=$ROOT/inst-$1 jp; jp=$(jmxport "$1")
  local tok=${TOK[$ip]:-}
  [ -n "$tok" ] || { log "NO TOKEN for $ip"; return 1; }
  rm -rf "$d"; mkdir -p "$d"/{data,commitlog,hints,saved_caches,logs}
  cp -r "$BUILD/conf" "$d/conf"
  local y=$d/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c1rring'/" \
    -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" \
    -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"$SEEDS\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" \
    -e "s|^key_cache_size:|key_cache_size: 0MiB|" \
    -e "s|^counter_cache_size:|counter_cache_size: 0MiB|" \
    "$y"
  echo "auto_bootstrap: false" >> "$y"
  echo "initial_token: $tok" >> "$y"
  printf 'dc=c\nrack=r1\n' > "$d/conf/cassandra-rackdc.properties"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jp\"/" "$d/conf/cassandra-env.sh"
  grep -qE "^listen_address: $ip" "$y" && grep -qE "^endpoint_snitch: GossipingPropertyFileSnitch" "$y" \
    && grep -qE "^JMX_PORT=\"$jp\"" "$d/conf/cassandra-env.sh" || { log "GEN FAIL $ip"; return 1; }
}

start_one(){
  local ip=$1 d=$ROOT/inst-$1
  ( ulimit -n 100000
    cd "$BUILD"
    CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" MAX_HEAP_SIZE="$XMX" HEAP_NEWSIZE="256M" \
      "$BUILD/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  log "launched $ip pid=$(cat "$d/cass.pid" 2>/dev/null) jmx=$(jmxport "$ip") xmx=$XMX dc=c"
}

alive(){ local p; p=$(cat "$ROOT/inst-$1/cass.pid" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

case "${1:-}" in
  aliasup)   IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do sudo ip addr add "$ip/24" dev $IFACE 2>/dev/null && log "alias +$ip" || log "alias $ip exists"; done ;;
  aliasdown) IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do sudo ip addr del "$ip/24" dev $IFACE 2>/dev/null && log "alias -$ip" || true; done ;;
  gen)       IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do gen_one "$ip" && log "gen $ip ok"; done ;;
  start)     IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do start_one "$ip"; sleep 3; done ;;
  status)    for d in $ROOT/inst-*; do ip=${d##*inst-}; if alive "$ip"; then echo "$ip UP pid=$(cat "$d/cass.pid")"; else echo "$ip DOWN"; fi; done ;;
  stop)      for d in $ROOT/inst-*; do ip=${d##*inst-}; p=$(cat "$d/cass.pid" 2>/dev/null); [ -n "$p" ] && kill "$p" 2>/dev/null && log "stop $ip pid=$p"; done; sleep 3
             pkill -f 'cassandra.logdir=/mydata/c1r/inst' 2>/dev/null; log "stop done" ;;
  *) echo "usage: peer-ctl2.sh {aliasup|aliasdown|gen|start|status|stop} [aliasCSV]"; exit 1;;
esac
