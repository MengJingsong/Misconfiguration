#!/usr/bin/env bash
# B19 3-b confirm (ms0625, 2026-11-23): stage-2 ctl.sh with ROOT=/mydata/s4/3b-B19, BUILD = a copy of the base in
# $ROOT/tree, an empty data dir per lifetime (T2 needs no template; NOTEMPLATE defaults to 1), scope units b3b19V-*, and
# authentication + authorization on (PasswordAuthenticator, CassandraAuthorizer, CassandraRoleManager). Capacity settings
# untouched (shipped defaults). Stage-2 header:
# B19 single-node controller (ms0625, Utah m400 aarch64, loopback 127.0.0.19, JMX 7319). Derived from B9 ctl.sh.
# Unpatched 5.0.9 build /mydata/s4/cassandra-base (read-only) or the diagnostic copy /mydata/s4/B19/patched (BUILD=).
# conf copied per arm; only environment keys change (cluster name, addresses, seeds, directories, JMX port).
#   ctl.sh gen | start | stop | pid | cg
# env: BUILD, XMX (default 2048M), DUMP (1 keep HeapDumpOnOOM in $D/dumps, 0 add -XX:-HeapDumpOnOutOfMemoryError),
#      VEXTRA (I1/I2 property only), NOTEMPLATE=1 (empty data dir, template creation only)
set -uo pipefail
BUILD=${BUILD:-/mydata/s4/3b-B19/tree}
ROOT=/mydata/s4/3b-B19
D=$ROOT/node
IP=127.0.0.19; JMXP=7319; CPUS=0-5
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
gen(){
  rm -rf "$D"; mkdir -p "$D"/{logs,dumps,data,commitlog,hints,saved_caches,cdc_raw}
  cp -r "$BUILD/conf" "$D/conf"
  local y=$D/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'b19'/" \
    -e "s/^listen_address: localhost/listen_address: $IP/" \
    -e "s/^rpc_address: localhost/rpc_address: $IP/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"$IP:7000\"|" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $D/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $D/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $D/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $D/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $D/cdc_raw|" \
    -e 's|^authenticator: AllowAllAuthenticator$|authenticator: PasswordAuthenticator|' \
    -e 's|^authorizer: AllowAllAuthorizer$|authorizer: CassandraAuthorizer|' \
    -e 's|^role_manager: .*$|role_manager: CassandraRoleManager|' \
    "$y"
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JMXP\"/" "$D/conf/cassandra-env.sh"
  grep -q "^listen_address: $IP" "$y" && grep -q "^commitlog_directory: $D/commitlog" "$y" && grep -q "^JMX_PORT=\"$JMXP\"" "$D/conf/cassandra-env.sh" \
    && grep -q "^authenticator: PasswordAuthenticator$" "$y" && grep -q "^authorizer: CassandraAuthorizer$" "$y" && grep -q "^role_manager: CassandraRoleManager$" "$y" \
    || { log "GEN FAIL"; return 1; }
  diff <(grep -vE '^\s*#|^\s*$' "$BUILD/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$D/yaml.diff"
  if [ "${NOTEMPLATE:-1}" != 1 ]; then
    [ -d "$ROOT/template/data" ] || { log "NO TEMPLATE"; return 1; }
    rsync -a "$ROOT/template/" "$D/"
  fi
  return 0
}
start(){
  local xmx=${XMX:-2048M}
  local extra="-XX:ErrorFile=$D/logs/hs_err_pid%p.log ${VEXTRA:-}"
  [ "${DUMP:-0}" = 1 ] || extra="$extra -XX:-HeapDumpOnOutOfMemoryError"
  cat > "$D/launch.sh" <<EOS
#!/usr/bin/env bash
ulimit -n 100000
cd "$D"
export CASSANDRA_CONF="$D/conf" CASSANDRA_LOG_DIR="$D/logs" CASSANDRA_HEAPDUMP_DIR="$D/dumps"
export MAX_HEAP_SIZE="$xmx" JVM_EXTRA_OPTS="$extra"
unset HEAP_NEWSIZE MAX_DIRECT_MEMORY_SIZE
exec taskset -c $CPUS "$BUILD/bin/cassandra" -f -p "$D/cass.pid" > "$D/logs/stdout.log" 2>&1
EOS
  chmod +x "$D/launch.sh"
  local unit="b3b19V-$(date +%s)"; echo "$unit" > "$D/unit"
  # safety scope only (non-binding): MemoryMax 48G, no swap for the measured process
  ( setsid nohup systemd-run --user --scope --quiet --unit="$unit" -p MemoryMax=48G -p MemorySwapMax=0 "$D/launch.sh" < /dev/null > "$D/logs/launch.log" 2>&1 & )
  local p=""; for _ in $(seq 30); do sleep 1; p=$(pidof_v); [ -n "$p" ] && break; done
  local cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)
  log "launched V pid=$p build=$BUILD xmx=$xmx dump=${DUMP:-0} vextra=[${VEXTRA:-}] unit=$unit memory.max=$(cat $cg/memory.max 2>/dev/null) swap.max=$(cat $cg/memory.swap.max 2>/dev/null)"
}
pidof_v(){ local p; p=$(cat "$D/cass.pid" 2>/dev/null); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; } || p=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); echo "$p"; }
stop(){
  local p u; p=$(pidof_v); u=$(cat "$D/unit" 2>/dev/null)
  if [ -n "$p" ]; then kill "$p" 2>/dev/null; for _ in $(seq 30); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
  pkill -9 -f "cassandra.logdir=$D/logs" 2>/dev/null
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped V (${p:-none})"
}
case "${1:-}" in
  gen) gen ;;
  start) start ;;
  stop) stop; true ;;
  pid) pidof_v ;;
  cg) p=$(pidof_v); [ -n "$p" ] && echo "/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null)" ;;
  *) echo "usage: $0 gen|start|stop|pid|cg" >&2; exit 2 ;;
esac
