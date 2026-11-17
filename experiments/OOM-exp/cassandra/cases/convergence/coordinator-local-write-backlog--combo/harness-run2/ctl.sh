#!/usr/bin/env bash
# S2 run 2 per-node Cassandra controller (runs ON the node). Utah m400, aarch64. Roles:
#   V   ms0640 10.10.1.2  victim: coordinator for every client write + replica (seed)
#   R1  ms0604 10.10.1.3  replica
#   R2  ms0611 10.10.1.4  replica (RF=3 arms only)
# Build /mydata/s2r2/cassandra (5.0.9, ant jar on ms0640, rsynced). Only environment settings are changed; every
# capacity, timeout, cache and hints setting stays at the shipped default (as run 1's ctl.sh).
# The JVM runs in a user scope with MemorySwapMax=0 (no memory limit: the budget is the Java heap) so the
# heap cannot be swapped (nodes have 8 GiB swap on). Linger must be enabled (arm.sh does it).
#   ctl.sh gen <V|R1|R2> <xmx> <dc> [key=value ...] | start <role> | stop <role> | pid <role> | cg <role>
set -uo pipefail
declare -A IP=([V]=10.10.1.2 [R1]=10.10.1.3 [R2]=10.10.1.4)
declare -A TOK=([V]=-9223372036854775808 [R1]=-3074457345618258603 [R2]=3074457345618258602)
B=/mydata/s2r2/cassandra
ROOT=/mydata/s2r2/inst
log(){ echo "[$(date '+%T')] $*"; }
gen(){
  local n=$1 xmx=$2 dc=$3; shift 3; local d=$ROOT/$n ip=${IP[$n]}
  rm -rf "$d"; mkdir -p "$d"/{logs,dumps,data,commitlog,hints,saved_caches}
  cp -r "$B/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 's2r2ring'/" -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"10.10.1.2:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  local kv k; for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  printf 'dc=%s\nrack=r1\n' "$dc" > "$d/conf/cassandra-rackdc.properties"
  echo "$xmx" > "$d/xmx"; diff "$B/conf/cassandra.yaml" "$y" > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" || { log "GEN FAIL $n"; return 1; }; log "gen $n xmx=$xmx dc=$dc extra=[$*]"
}
start(){
  local n=$1 d=$ROOT/$1 u="s2r2-$1-$(date +%s)"
  echo "$u" > "$d/unit"
  ( ulimit -n 100000; cd "$B"; CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
    MAX_HEAP_SIZE="$(cat $d/xmx)" HEAP_NEWSIZE="256M" \
    systemd-run --user --scope --quiet --unit="$u" -p MemorySwapMax=0 -- "$B/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  sleep 2; local p; p=$(cat $d/cass.pid 2>/dev/null)
  local cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)
  echo "$cg" > "$d/cgroup"
  log "launched $n pid=$p unit=$u cgroup=$cg swap.max=$(cat $cg/memory.swap.max 2>/dev/null) memory.max=$(cat $cg/memory.max 2>/dev/null)"
}
stop(){
  local p u; p=$(cat $ROOT/$1/cass.pid 2>/dev/null); u=$(cat $ROOT/$1/unit 2>/dev/null)
  if [ -n "$p" ]; then
    kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null
  fi
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped $1 (${p:-none})"
}
case "${1:-}" in gen) shift; gen "$@";; start) start "$2";; stop) stop "$2";; pid) cat $ROOT/$2/cass.pid;; cg) cat $ROOT/$2/cgroup;; *) exit 2;; esac
