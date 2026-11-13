#!/usr/bin/env bash
# C1 run-4 single-host 10-instance ring controller (pc96, loopback addresses), data on tmpfs.
#   V  127.0.0.21 dc=v  victim (measured), JMX 7221, in a systemd --user scope (MemoryMax safety only)
#   F  127.0.0.22 dc=f  fast co-replica (acks CL=ONE), JMX 7222
#   C1..C8 127.0.0.31-38 dc=c coordinator-only instances (own no replica), JMX 7231-7238
# Capacity settings (receive/send queues, caches, memtable, concurrent_writes) are NOT set: defaults.
# Deviations applied to all instances: hinted_handoff_enabled=false; commitlog_total_space=2048MiB (tmpfs).
#   ctl.sh gen <name> <xmx> [key=value ...] | start <name> | stop <name|all> | status | pid <name>
# env for start V: DIRECT=<MiB> (victim MaxDirectMemorySize), BYTEMAN=<btm file or empty>
set -uo pipefail
BUILD=/mydata/b6/cassandra          # read-only reuse of the unpatched 5.0.9 build
ROOT=/mydata/c1r4/ring
SHM=/mydata/c1r4/shm                 # tmpfs mount for data/commitlog
declare -A IP=([V]=127.0.0.21 [F]=127.0.0.22 [C1]=127.0.0.31 [C2]=127.0.0.32 [C3]=127.0.0.33 [C4]=127.0.0.34 [C5]=127.0.0.35 [C6]=127.0.0.36 [C7]=127.0.0.37 [C8]=127.0.0.38)
declare -A DC=([V]=v [F]=f)
declare -A JMX=([V]=7221 [F]=7222 [C1]=7231 [C2]=7232 [C3]=7233 [C4]=7234 [C5]=7235 [C6]=7236 [C7]=7237 [C8]=7238)
declare -A CPUS=([V]=0-7 [F]=8-15)
ALL="V F C1 C2 C3 C4 C5 C6 C7 C8"
# evenly spaced tokens, 10 instances
tok(){ local i=$1; python3 -c "print(-2**63 + $i * (2**64 // 10))"; }
declare -A IDX=([V]=0 [F]=1 [C1]=2 [C2]=3 [C3]=4 [C4]=5 [C5]=6 [C6]=7 [C7]=8 [C8]=9)
log(){ echo "[$(date '+%T')] $*"; }

gen(){
  local n=$1 xmx=$2; shift 2
  local d=$ROOT/$n ip=${IP[$n]} dd=$SHM/$n
  rm -rf "$d" "$dd"; mkdir -p "$d"/{logs,dumps} "$dd"/{data,commitlog,hints,saved_caches}
  cp -r "$BUILD/conf" "$d/conf"
  local y=$d/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c1r4ring'/" \
    -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" \
    -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"127.0.0.21:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $dd/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $dd/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $dd/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $dd/saved_caches|" \
    "$y"
  { echo "auto_bootstrap: false"; echo "initial_token: $(tok ${IDX[$n]})"; } >> "$y"
  # DEFAULTS=1 (condition D, added 2026-11-12 10:35): keep hinted handoff on and commitlog_total_space default
  if [ "${DEFAULTS:-0}" != 1 ]; then
    sed -i "s|^hinted_handoff_enabled: true|hinted_handoff_enabled: false|" "$y"; echo "commitlog_total_space: 2048MiB" >> "$y"
  fi
  local kv k
  for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  printf 'dc=%s\nrack=r1\n' "${DC[$n]:-c}" > "$d/conf/cassandra-rackdc.properties"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"${JMX[$n]}\"/" "$d/conf/cassandra-env.sh"
  echo "$xmx" > "$d/xmx"
  grep -q "^listen_address: $ip" "$y" && { [ "${DEFAULTS:-0}" = 1 ] || grep -q "^hinted_handoff_enabled: false" "$y"; } \
    && grep -q "^JMX_PORT=\"${JMX[$n]}\"" "$d/conf/cassandra-env.sh" || { log "GEN FAIL $n"; return 1; }
  diff <(grep -vE '^\s*#|^\s*$' "$BUILD/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$d/yaml.diff"; return 0
}

start(){
  local n=$1 d=$ROOT/$1 xmx extra="" cpus
  xmx=$(cat "$d/xmx")
  cpus=${CPUS[$n]:-16-23}
  if [ "$n" = V ]; then
    local direct=${DIRECT:?DIRECT required for V}
    extra="-XX:MaxDirectMemorySize=${direct}M -XX:-HeapDumpOnOutOfMemoryError"
    [ "${HEAPDUMP:-0}" = 1 ] && extra="-XX:MaxDirectMemorySize=${direct}M -XX:+HeapDumpOnOutOfMemoryError"   # amendment 4
    if [ -n "${BYTEMAN:-}" ]; then
      local bm=$BUILD/build/lib/jars/byteman-4.0.20.jar
      extra="$extra -javaagent:$bm=script:${BYTEMAN},listener:true,port:9091,address:127.0.0.1"
    fi
    cat > "$d/launch.sh" <<EOF
#!/usr/bin/env bash
ulimit -n 100000
cd "$BUILD"
export CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps"
export MAX_HEAP_SIZE="$xmx" HEAP_NEWSIZE="512M" JVM_EXTRA_OPTS="$extra"
echo \$\$ > "$d/scope.pid"
exec taskset -c $cpus "$BUILD/bin/cassandra" -f -p "$d/cass.pid"
EOF
    chmod +x "$d/launch.sh"
    local unit="c1r4V-$(date +%s)"; echo "$unit" > "$d/unit"
    systemd-run --user --scope --unit="$unit" -p MemoryMax=12G -p MemorySwapMax=0 "$d/launch.sh" > "$d/logs/launch.log" 2>&1 &
    sleep 4
  else
    ( ulimit -n 100000
      cd "$BUILD"
      CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="$d/dumps" \
      MAX_HEAP_SIZE="$xmx" HEAP_NEWSIZE="256M" JVM_EXTRA_OPTS="-XX:-HeapDumpOnOutOfMemoryError" \
        taskset -c $cpus "$BUILD/bin/cassandra" -p "$d/cass.pid" >"$d/logs/launch.log" 2>&1 )
  fi
  log "launched $n pid=$(cat "$d/cass.pid" 2>/dev/null) xmx=$xmx cpus=$cpus $extra"
}

pidof_n(){ local p; p=$(cat "$ROOT/$1/cass.pid" 2>/dev/null); [ -z "$p" ] && p=$(pgrep -f "cassandra.logdir=$ROOT/$1/logs" | head -1); echo "$p"; }
alive(){ local p; p=$(pidof_n "$1"); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }
cgdir(){ local p; p=$(pidof_n V); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)"; }

stop(){
  local n p
  for n in "$@"; do
    p=$(pidof_n "$n"); [ -n "$p" ] || continue
    kill "$p" 2>/dev/null; for _ in $(seq 20); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    kill -9 "$p" 2>/dev/null; log "stopped $n ($p)"
  done
}

case "${1:-}" in
  gen) shift; gen "$@" ;;
  start) start "$2" ;;
  stop) if [ "$2" = all ]; then stop C8 C7 C6 C5 C4 C3 C2 C1 F V; pkill -f "cassandra.logdir=$ROOT/" 2>/dev/null; else stop "$2"; fi ;;
  status) for n in $ALL; do if alive $n; then echo "$n UP pid=$(pidof_n $n)"; else echo "$n DOWN"; fi; done ;;
  pid) pidof_n "$2" ;;
  cg) cgdir ;;
  *) echo "usage: $0 gen|start|stop|status|pid|cg" >&2; exit 2 ;;
esac
