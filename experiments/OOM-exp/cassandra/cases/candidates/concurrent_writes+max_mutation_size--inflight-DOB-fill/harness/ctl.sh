#!/usr/bin/env bash
# U1 single-node controller (pc96, loopback 127.0.0.71, JMX 7271). Derived from S1 ctl.sh (C1 run 4).
# Read-only reuse of the unpatched 5.0.9 build /mydata/b6/cassandra; conf copied per arm; data/commitlog/hints on
# local disk /mydata/u1/node (HDD RAID, not tmpfs: S1 amendment 1). Capacity settings are NOT set (shipped yaml);
# only environment keys are changed, plus VEXTRA ("key=value ...", control/intervention arms only).
#   ctl.sh gen | start | stop | pid | cg
# env for start: DIRECT=<MiB>|auto (auto: no -XX:MaxDirectMemorySize from us; cassandra-env.sh resolves it),
#                XMX (default 2048M), VJVM (extra JVM options, intervention arms only)
set -uo pipefail
BUILD=/mydata/b6/cassandra
D=/mydata/u1/node            # conf, logs, dumps, data (wiped by gen)
IP=127.0.0.71; JMXP=7271; CPUS=0-15
log(){ echo "[$(date '+%T')] $*"; }
gen(){
  rm -rf "$D"; mkdir -p "$D"/{logs,dumps,data,commitlog,hints,saved_caches,cdc_raw}
  cp -r "$BUILD/conf" "$D/conf"
  local y=$D/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'u1'/" \
    -e "s/^listen_address: localhost/listen_address: $IP/" \
    -e "s/^rpc_address: localhost/rpc_address: $IP/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"$IP:7000\"|" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $D/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $D/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $D/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $D/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $D/cdc_raw|" \
    "$y"
  local kv k
  for kv in ${VEXTRA:-}; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JMXP\"/" "$D/conf/cassandra-env.sh"
  grep -q "^listen_address: $IP" "$y" && grep -q "^commitlog_directory: $D/commitlog" "$y" && grep -q "^JMX_PORT=\"$JMXP\"" "$D/conf/cassandra-env.sh" \
    || { log "GEN FAIL"; return 1; }
  diff <(grep -vE '^\s*#|^\s*$' "$BUILD/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$D/yaml.diff"; return 0
}
start(){
  local extra="${VJVM:-}" xmx=${XMX:-2048M} direct=${DIRECT:?DIRECT required (MiB or auto)}
  [ "$direct" != auto ] && extra="-XX:MaxDirectMemorySize=${direct}M $extra"
  extra="$extra -XX:ErrorFile=$D/logs/hs_err_pid%p.log"
  cat > "$D/launch.sh" <<EOS
#!/usr/bin/env bash
ulimit -n 100000
cd "$D"
export CASSANDRA_CONF="$D/conf" CASSANDRA_LOG_DIR="$D/logs" CASSANDRA_HEAPDUMP_DIR="$D/dumps"
export MAX_HEAP_SIZE="$xmx" JVM_EXTRA_OPTS="$extra"
unset HEAP_NEWSIZE MAX_DIRECT_MEMORY_SIZE
exec taskset -c $CPUS "$BUILD/bin/cassandra" -f -p "$D/cass.pid"
EOS
  chmod +x "$D/launch.sh"
  local unit="u1V-$(date +%s)"; echo "$unit" > "$D/unit"
  # safety scope only (non-binding): MemoryMax 44G as S1 after its amendment 4; no swap
  systemd-run --user --scope --unit="$unit" -p MemoryMax=44G -p MemorySwapMax=0 "$D/launch.sh" > "$D/logs/launch.log" 2>&1 &
  sleep 4; log "launched V pid=$(cat "$D/cass.pid" 2>/dev/null) xmx=$xmx direct=$direct extra=[$extra] unit=$unit"
}
pidof_v(){ local p; p=$(cat "$D/cass.pid" 2>/dev/null); [ -n "$p" ] && kill -0 "$p" 2>/dev/null || p=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); echo "$p"; }
stop(){
  local p; p=$(pidof_v); [ -n "$p" ] || return 0
  kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
  kill -9 "$p" 2>/dev/null; log "stopped V ($p)"
}
case "${1:-}" in
  gen) gen ;;
  start) start ;;
  stop) stop; pkill -f "cassandra.logdir=$D/logs" 2>/dev/null; true ;;
  pid) pidof_v ;;
  cg) p=$(pidof_v); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)" ;;
  *) echo "usage: $0 gen|start|stop|pid|cg" >&2; exit 2 ;;
esac
