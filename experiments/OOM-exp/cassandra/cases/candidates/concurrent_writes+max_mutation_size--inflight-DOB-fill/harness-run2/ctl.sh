#!/usr/bin/env bash
# U1 run 2 per-node Cassandra controller (runs ON the node; copied to /mydata/u1r2/h/). Utah m400, aarch64.
# Roles (one instance per node):
#   V   ms0625 10.10.1.1  victim: the only replica (dc v, keyspace u1r2 = NTS {v:1}); seed
#   C1  ms0640 10.10.1.2  coordinator (dc c, owns no replica of u1r2)
#   C2  ms0604 10.10.1.3  coordinator
#   C3  ms0611 10.10.1.4  coordinator
#   C4  ms0617 10.10.1.5  coordinator
#   C5..C8 (amendment 2): second coordinator on ms0640/0604/0611/0617 at alias IPs 10.10.1.12-.15, JMX port 7299
# Build /mydata/u1r2/cassandra (copy of the S2 run-2 aarch64 build of the pinned 5.0.9 source, read-only).
# Only environment keys are changed (cluster name, addresses, seeds, snitch, directories, num_tokens/initial_token,
# auto_bootstrap); every capacity, timeout, cache and hints setting stays at the shipped default.
# Extra yaml "k=v" pairs are passed only for control / intervention arms (VEXTRA in arm.sh).
#   ctl.sh gen <role> <xmx> <dc> [key=value ...] | start <role> | stop <role> | pid <role> | cg <role>
# env for start: DIRECT=<MiB>|auto (V only; MiB -> MAX_DIRECT_MEMORY_SIZE, the documented cassandra-env.sh
#                override; auto -> unset, cassandra-env.sh resolves it), VJVM (extra JVM options, V intervention only)
set -uo pipefail
declare -A IP=([V]=10.10.1.1 [C1]=10.10.1.2 [C2]=10.10.1.3 [C3]=10.10.1.4 [C4]=10.10.1.5 [C5]=10.10.1.12 [C6]=10.10.1.13 [C7]=10.10.1.14 [C8]=10.10.1.15)
declare -A TOK=([V]=-9223372036854775808 [C1]=-5534023222112865485 [C2]=-1844674407370955162 [C3]=1844674407370955161 [C4]=5534023222112865484 [C5]=-3689348814741910323 [C6]=0 [C7]=3689348814741910322 [C8]=7378697629483820644)
B=/mydata/u1r2/cassandra
ROOT=/mydata/u1r2/inst
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
gen(){
  local n=$1 xmx=$2 dc=$3; shift 3; local d=$ROOT/$n ip=${IP[$n]}
  rm -rf "$d"; mkdir -p "$d"/{logs,dumps,data,commitlog,hints,saved_caches,cdc_raw}
  cp -r "$B/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'u1r2'/" -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"10.10.1.1:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $d/cdc_raw|" "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: ${TOK[$n]}"; } >> "$y"
  local kv k; for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  printf 'dc=%s\nrack=r1\n' "$dc" > "$d/conf/cassandra-rackdc.properties"
  echo "$xmx" > "$d/xmx"
  case $n in C5|C6|C7|C8) sed -i 's/^JMX_PORT="7199"/JMX_PORT="7299"/' "$d/conf/cassandra-env.sh" ;; esac
  diff <(grep -vE '^\s*#|^\s*$' "$B/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" && grep -q "^commitlog_directory: $d/commitlog" "$y" || { log "GEN FAIL $n"; return 1; }
  log "gen $n xmx=$xmx dc=$dc extra=[$*]"
}
start(){
  local n=$1 d=$ROOT/$1 u="u1r2-$1-$(date +%s)" xmx; xmx=$(cat "$d/xmx")
  local mdm="" extra="-XX:ErrorFile=$d/logs/hs_err_pid%p.log" scope="-p MemorySwapMax=0"
  if [ "$n" = V ]; then
    local direct=${DIRECT:?DIRECT required for V}
    [ "$direct" != auto ] && mdm="${direct}M"
    extra="$extra ${VJVM:-}"
    scope="-p MemoryMax=40G -p MemorySwapMax=0"   # safety only (non-binding): heap 2 GiB + direct <= 16 GiB auto
  else
    extra="$extra -XX:-HeapDumpOnOutOfMemoryError"  # coordinators: no 8 GiB dumps on their disks
  fi
  cat > "$d/launch.sh" <<EOS
#!/usr/bin/env bash
ulimit -n 100000
cd "$d"
export CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps"
export MAX_HEAP_SIZE="$xmx" JVM_EXTRA_OPTS="$extra"
unset HEAP_NEWSIZE MAX_DIRECT_MEMORY_SIZE
[ -n "$mdm" ] && export MAX_DIRECT_MEMORY_SIZE="$mdm"
exec "$B/bin/cassandra" -f -p "$d/cass.pid"
EOS
  chmod +x "$d/launch.sh"; echo "$u" > "$d/unit"
  nohup systemd-run --user --scope --quiet --unit="$u" $scope "$d/launch.sh" > "$d/logs/launch.log" 2>&1 < /dev/null &
  local p=""; for _ in $(seq 20); do sleep 1; p=$(pidof_n "$n"); [ -n "$p" ] && break; done
  local cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null); echo "$cg" > "$d/cgroup"
  log "launched $n pid=$p xmx=$xmx direct=${DIRECT:-auto} mdm=[$mdm] extra=[$extra] unit=$u memory.max=$(cat $cg/memory.max 2>/dev/null) swap.max=$(cat $cg/memory.swap.max 2>/dev/null)"
}
pidof_n(){ local p; p=$(cat "$ROOT/$1/cass.pid" 2>/dev/null); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; } || p=$(pgrep -f "cassandra.logdir=$ROOT/$1/logs" | head -1); echo "$p"; }
stop(){
  local p u; p=$(pidof_n "$1"); u=$(cat $ROOT/$1/unit 2>/dev/null)
  if [ -n "$p" ]; then kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
  pkill -9 -f "cassandra.logdir=$ROOT/$1/logs" 2>/dev/null
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped $1 (${p:-none})"
}
case "${1:-}" in
  gen) shift; gen "$@" ;; start) start "$2" ;; stop) stop "$2" ;; pid) pidof_n "$2" ;; cg) p=$(pidof_n "$2"); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)" ;;
  *) echo "usage: $0 gen|start|stop|pid|cg" >&2; exit 2 ;;
esac
