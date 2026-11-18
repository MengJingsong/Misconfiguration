#!/usr/bin/env bash
# C7 per-node Cassandra controller (runs ON the node; copied to /mydata/s4/c7-w3/h/). Utah m400, aarch64.
# Adapted from R7's ctl.sh (copy, not edit). Work dir /mydata/s4/c7-w3, cluster 'c7', 4 instances:
#   n1 ms0625 10.10.1.1  JMX 7199  seed, repair coordinator, VICTIM (DIRECT MiB)
#   n3 ms0625 10.10.1.81 JMX 7299  peer (alias IP)
#   n2 ms0640 10.10.1.2  JMX 7199  peer
#   n4 ms0640 10.10.1.82 JMX 7299  peer (alias IP)
# Only environment keys change (cluster name, addresses, seeds, directories, auto_bootstrap). num_tokens 16,
# allocate_tokens_for_local_replication_factor 3, SimpleSnitch and every capacity stay at the shipped default.
#   ctl.sh gen <n> [key=value ...] | start <n> | stop <n> | pid <n> | cg <n>
# env for start: DIRECT=<MiB> (n1: victim direct limit; peers always 4096)
set -uo pipefail
declare -A IP=([n1]=10.10.1.1 [n2]=10.10.1.2 [n3]=10.10.1.81 [n4]=10.10.1.82)
B=/mydata/s4/cassandra-base
ROOT=/mydata/s4/c7-w3/inst
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
gen(){
  local n=$1; shift; local d=$ROOT/$n ip=${IP[$n]}
  mkdir -p "$d"/{logs,dumps,data,commitlog,hints,saved_caches,cdc_raw}
  rm -rf "$d/conf"; cp -r "$B/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c7'/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"10.10.1.1:7000\"|" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $d/cdc_raw|" "$y"
  echo "auto_bootstrap: false" >> "$y"
  local kv k; for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  case $n in n3|n4) sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"7299\"/" "$d/conf/cassandra-env.sh" ;; esac
  grep '^JMX_PORT=' "$d/conf/cassandra-env.sh" > "$d/jmxport"
  diff <(grep -vE '^\s*#|^\s*$' "$B/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" && grep -q "^commitlog_directory: $d/commitlog" "$y" || { log "GEN FAIL $n"; return 1; }
  log "gen $n extra=[$*]"
}
start(){
  local n=$1 d=$ROOT/$1 u="c7-$1-$(date +%s)"
  local mdm extra="-XX:ErrorFile=$d/logs/hs_err_pid%p.log" scope="-p MemorySwapMax=0"
  if [ "$n" = n1 ]; then
    mdm="${DIRECT:?DIRECT required for n1}M"
    scope="-p MemoryMax=24G -p MemorySwapMax=0"   # safety only (non-binding)
  else
    mdm="4096M"; extra="$extra -XX:-HeapDumpOnOutOfMemoryError"
  fi
  cat > "$d/launch.sh" <<EOS
#!/usr/bin/env bash
ulimit -n 100000
cd "$d"
export CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps"
export MAX_HEAP_SIZE="2048M" JVM_EXTRA_OPTS="$extra"
unset HEAP_NEWSIZE
export MAX_DIRECT_MEMORY_SIZE="$mdm"
exec "$B/bin/cassandra" -f -p "$d/cass.pid"
EOS
  chmod +x "$d/launch.sh"; echo "$u" > "$d/unit"; rm -f "$d/cass.pid"
  ( setsid nohup systemd-run --user --scope --quiet --unit="$u" $scope "$d/launch.sh" < /dev/null > "$d/logs/launch.log" 2>&1 & )
  local p=""; for _ in $(seq 20); do sleep 1; p=$(pidof_n "$n"); [ -n "$p" ] && break; done
  local cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null); echo "$cg" > "$d/cgroup"
  log "launched $n pid=$p mdm=[$mdm] extra=[$extra] unit=$u memory.max=$(cat $cg/memory.max 2>/dev/null) swap.max=$(cat $cg/memory.swap.max 2>/dev/null)"
}
pidof_n(){ local p; p=$(cat "$ROOT/$1/cass.pid" 2>/dev/null); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; } || p=$(pgrep -f "cassandra.logdir=$ROOT/$1/logs" | head -1); echo "$p"; }
stop(){
  local p u; p=$(pidof_n "$1"); u=$(cat $ROOT/$1/unit 2>/dev/null)
  if [ -n "$p" ]; then kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped $1 (${p:-none})"
}
case "${1:-}" in
  gen) shift; gen "$@" ;; start) start "$2" ;; stop) stop "$2" ;; pid) pidof_n "$2" ;; cg) p=$(pidof_n "$2"); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)" ;;
  *) echo "usage: $0 gen|start|stop|pid|cg" >&2; exit 2 ;;
esac
