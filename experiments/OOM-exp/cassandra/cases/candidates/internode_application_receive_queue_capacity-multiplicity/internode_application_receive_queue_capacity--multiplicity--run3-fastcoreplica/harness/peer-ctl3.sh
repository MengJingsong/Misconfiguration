#!/usr/bin/env bash
# C1 run3 peer-host controller — runs ON each remote host (apt179/138/190/149).
# Two instance roles, both own the correct dc so NTS {v:1,f:1} places replicas right:
#   role=fast  (dc=f): the FAST co-replica, 10.10.1.2 on apt179. Normal/fast apply, ample
#              heap, NO byteman -> satisfies CL=ONE for every write so the client never
#              blocks on the slow victim. This is the run-3 decoupling mechanism.
#   role=coord (dc=c): coordinator-only instances (own NO replica). N active coordinators
#              = N loaded inbound handlers on the victim = the multiplicity N.
# All instances: GossipingPropertyFileSnitch, explicit initial_token, hinted_handoff off,
# distinct LAN IP alias + JMX port, own dirs under /mydata/c1r3.
#   peer-ctl3.sh aliasup <ipCSV> | aliasdown <ipCSV>
#   peer-ctl3.sh gen <role> <ipCSV> [xmx]   # role=fast|coord
#   peer-ctl3.sh start <ipCSV> [xmx] | status | stop | heap <ipCSV>
set -uo pipefail
BUILD=$HOME/cassandra-c1
ROOT=/mydata/c1r3
IFACE=enp8s0d1
SEEDS='10.10.1.1:7000,10.10.1.2:7000'
log(){ echo "[$(date '+%T')] $*"; }
jmxport(){ echo $((17000 + ${1##*.})); }
# evenly-spaced tokens, 10-instance ring (victim i0=min). fast=i1; coordinators i2..i9.
declare -A TOK=(
 [10.10.1.2]=-7378697629483820646
 [10.10.1.31]=-5534023222112865484 [10.10.1.32]=-3689348814741910322
 [10.10.1.33]=-1844674407370955160 [10.10.1.41]=2
 [10.10.1.42]=1844674407370955164  [10.10.1.43]=3689348814741910326
 [10.10.1.51]=5534023222112865488  [10.10.1.52]=7378697629483820650 )
declare -A DC=( [10.10.1.2]=f )   # everything else defaults to c

gen_one(){
  local ip=$1 role=$2 xmx=$3 d=$ROOT/inst-$1 jp; jp=$(jmxport "$1")
  local tok=${TOK[$ip]:-}; [ -n "$tok" ] || { log "NO TOKEN for $ip"; return 1; }
  local dc=c; [ "$role" = fast ] && dc=f
  rm -rf "$d"; mkdir -p "$d"/{data,commitlog,hints,saved_caches,logs}
  cp -r "$BUILD/conf" "$d/conf"
  local y=$d/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c1r3ring'/" \
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
    -e "s|^hinted_handoff_enabled: true|hinted_handoff_enabled: false|" \
    "$y"
  echo "auto_bootstrap: false" >> "$y"
  echo "initial_token: $tok" >> "$y"
  printf 'dc=%s\nrack=r1\n' "$dc" > "$d/conf/cassandra-rackdc.properties"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$jp\"/" "$d/conf/cassandra-env.sh"
  echo "$xmx" > "$d/xmx"
  grep -qE "^listen_address: $ip" "$y" && grep -qE "^endpoint_snitch: GossipingPropertyFileSnitch" "$y" \
    && grep -qE "^hinted_handoff_enabled: false" "$y" && grep -qE "^JMX_PORT=\"$jp\"" "$d/conf/cassandra-env.sh" \
    || { log "GEN FAIL $ip"; return 1; }
  log "gen $ip ok (role=$role dc=$dc xmx=$xmx tok=$tok)"
}

start_one(){
  local ip=$1 d=$ROOT/inst-$1 xmx; xmx=$(cat "$d/xmx" 2>/dev/null || echo 1G)
  ( ulimit -n 100000
    cd "$BUILD"
    CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" MAX_HEAP_SIZE="$xmx" HEAP_NEWSIZE="256M" \
      "$BUILD/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  log "launched $ip pid=$(cat "$d/cass.pid" 2>/dev/null) jmx=$(jmxport "$ip") xmx=$xmx"
}

alive(){ local p; p=$(cat "$ROOT/inst-$1/cass.pid" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }

case "${1:-}" in
  aliasup)   IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do sudo ip addr add "$ip/24" dev $IFACE 2>/dev/null && log "alias +$ip" || log "alias $ip exists"; done ;;
  aliasdown) IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do sudo ip addr del "$ip/24" dev $IFACE 2>/dev/null && log "alias -$ip" || true; done ;;
  gen)       role=$2; IFS=',' read -ra A <<< "$3"; xmx=${4:-1G}; for ip in "${A[@]}"; do gen_one "$ip" "$role" "$xmx"; done ;;
  start)     IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do start_one "$ip"; sleep 3; done ;;
  status)    for d in $ROOT/inst-*; do ip=${d##*inst-}; if alive "$ip"; then echo "$ip UP pid=$(cat "$d/cass.pid")"; else echo "$ip DOWN"; fi; done ;;
  heap)      IFS=',' read -ra A <<< "$2"; for ip in "${A[@]}"; do jp=$(jmxport "$ip"); echo -n "$ip "; "$BUILD/bin/nodetool" -h 127.0.0.1 -p "$jp" info 2>/dev/null | grep -E 'Heap Memory'; done ;;
  stop)      for d in $ROOT/inst-*; do ip=${d##*inst-}; p=$(cat "$d/cass.pid" 2>/dev/null); [ -n "$p" ] && kill "$p" 2>/dev/null && log "stop $ip pid=$p"; done; sleep 3
             pkill -f 'cassandra.logdir=/mydata/c1r3/inst' 2>/dev/null; log "stop done" ;;
  *) echo "usage: peer-ctl3.sh {aliasup|aliasdown|gen <role> <ipCSV> [xmx]|start <ipCSV>|status|heap <ipCSV>|stop}"; exit 1;;
esac
