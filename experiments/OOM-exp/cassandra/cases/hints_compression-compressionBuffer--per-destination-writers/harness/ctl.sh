#!/usr/bin/env bash
# C5 stage 2: per-instance controller, runs ON ms0604 (Utah m400, aarch64). Copied to /mydata/s4/c5-w1/h/.
#   ctl.sh gen A <direct MiB> [key=value ...]        victim A (127.0.5.1, dc1, token 1, JMX 7299, heap 2048M)
#   ctl.sh gen <j> 0                                  dc2 node j (127.0.5.(100+j), JMX 7300+j, heap 384M, direct 256M)
#   ctl.sh start <name>                               env for A: JEXTRA (extra JVM options), DUMPDIR (heap dump dir)
#   ctl.sh stop <name> | kill9 <name> | pid <name>
# Only environment/topology keys are changed (cluster name, addresses, seeds, snitch, directories, num_tokens,
# initial_token, auto_bootstrap, start_native_transport on dc2). Extra key=value pairs (A only) carry the
# supporting setting hints_compression. Every capacity, timeout, cache and hints limit stays at the shipped default.
set -uo pipefail
B=/mydata/s4/cassandra-base
ROOT=/mydata/s4/c5-w1
INST=$ROOT/inst
log(){ echo "[$(TZ=America/New_York date '+%T')] $*"; }
ip_of(){ [ "$1" = A ] && echo 127.0.5.1 || echo 127.0.5.$((100 + $1)); }
jmx_of(){ [ "$1" = A ] && echo 7299 || echo $((7300 + $1)); }
tok_of(){ [ "$1" = A ] && echo 1 || python3 -c "print(-2**63 + $1 * 2**58 + 2**57)"; }
gen(){
  local n=$1 direct=$2; shift 2; local d=$INST/$n ip; ip=$(ip_of "$n")
  rm -rf "$d"; mkdir -p "$d"/{logs,data,commitlog,hints,saved_caches,cdc_raw}
  cp -r "$B/conf" "$d/conf"; local y=$d/conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c5'/" -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^allocate_tokens_for_local_replication_factor: 3/# allocate_tokens_for_local_replication_factor: 3/" \
    -e "s/^listen_address: localhost/listen_address: $ip/" -e "s/^rpc_address: localhost/rpc_address: $ip/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"127.0.5.1:7000\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" -e "s|^#     - /var/lib/cassandra/data|    - $d/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $d/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $d/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $d/saved_caches|" \
    -e "s|^# cdc_raw_directory: /var/lib/cassandra/cdc_raw|cdc_raw_directory: $d/cdc_raw|" "$y"
  echo "initial_token: $(tok_of "$n")" >> "$y"
  if [ "$n" != A ]; then
    echo "auto_bootstrap: false" >> "$y"
    sed -i "s/^start_native_transport: true/start_native_transport: false/" "$y"
    printf 'dc=dc2\nrack=rack1\n' > "$d/conf/cassandra-rackdc.properties"
    echo 384M > "$d/xmx"; echo 256 > "$d/direct"
  else
    printf 'dc=dc1\nrack=rack1\n' > "$d/conf/cassandra-rackdc.properties"
    echo 2048M > "$d/xmx"; echo "$direct" > "$d/direct"
  fi
  local kv k; for kv in "$@"; do k=${kv%%=*}; sed -i "/^$k:/d" "$y"; echo "$k: ${kv#*=}" >> "$y"; done
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$(jmx_of "$n")\"/" "$d/conf/cassandra-env.sh"
  diff <(grep -vE '^\s*#|^\s*$' "$B/conf/cassandra.yaml") <(grep -vE '^\s*#|^\s*$' "$y") > "$d/yaml.diff"
  grep -q "^listen_address: $ip" "$y" && grep -q "^commitlog_directory: $d/commitlog" "$y" || { log "GEN FAIL $n"; return 1; }
  log "gen $n ip=$ip jmx=$(jmx_of "$n") token=$(tok_of "$n") extra=[$*]"
}
start(){
  local n=$1 d=$INST/$1 xmx direct; xmx=$(cat "$d/xmx"); direct=$(cat "$d/direct")
  local extra="-XX:ErrorFile=$d/logs/hs_err_pid%p.log"
  if [ "$n" = A ]; then extra="$extra ${JEXTRA:-}"; else extra="$extra -XX:-HeapDumpOnOutOfMemoryError"; fi
  cat > "$d/launch.sh" <<EOS
#!/usr/bin/env bash
ulimit -n 100000 2>/dev/null || ulimit -n 65536
cd "$d"
export CASSANDRA_CONF="$d/conf" CASSANDRA_LOG_DIR="$d/logs" CASSANDRA_HEAPDUMP_DIR="${DUMPDIR:-$d/logs}"
export MAX_HEAP_SIZE="$xmx" MAX_DIRECT_MEMORY_SIZE="${direct}M" JVM_EXTRA_OPTS="$extra"
unset HEAP_NEWSIZE
exec "$B/bin/cassandra" -f -p "$d/cass.pid"
EOS
  chmod +x "$d/launch.sh"; rm -f "$d/cass.pid"
  if [ "$n" = A ]; then
    local u="c5-A-$(date +%s)"; echo "$u" > "$d/unit"
    ( setsid nohup systemd-run --user --scope --quiet --unit="$u" -p MemorySwapMax=0 "$d/launch.sh" < /dev/null > "$d/logs/launch.log" 2>&1 & )
  else
    ( setsid nohup "$d/launch.sh" < /dev/null > "$d/logs/launch.log" 2>&1 & )
  fi
  local p=""; for _ in $(seq 30); do sleep 1; p=$(pidof_n "$n"); [ -n "$p" ] && break; done
  if [ "$n" = A ]; then
    local cg=/sys/fs/cgroup$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null); echo "$cg" > "$d/cgroup"
    log "launched A pid=$p xmx=$xmx direct=${direct}M extra=[$extra] cg=$cg swap.max=$(cat $cg/memory.swap.max 2>/dev/null) memory.max=$(cat $cg/memory.max 2>/dev/null)"
  else
    log "launched $n pid=$p"
  fi
}
pidof_n(){ local p; p=$(cat "$INST/$1/cass.pid" 2>/dev/null); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; } || p=$(pgrep -f "cassandra.logdir=$INST/$1/logs" | head -1); echo "$p"; }
stop(){
  local p u; p=$(pidof_n "$1"); u=$(cat $INST/$1/unit 2>/dev/null)
  if [ -n "$p" ]; then kill "$p" 2>/dev/null; for _ in $(seq 40); do kill -0 "$p" 2>/dev/null || break; sleep 1; done; kill -9 "$p" 2>/dev/null; fi
  [ -n "$u" ] && systemctl --user stop "$u.scope" 2>/dev/null
  log "stopped $1 (${p:-none})"
}
kill9(){ local p; p=$(pidof_n "$1"); [ -n "$p" ] && kill -9 "$p"; log "kill -9 $1 (${p:-none})"; }
case "${1:-}" in
  gen) shift; gen "$@" ;; start) start "$2" ;; stop) stop "$2" ;; kill9) kill9 "$2" ;; pid) pidof_n "$2" ;;
  *) echo "usage: $0 gen|start|stop|kill9|pid" >&2; exit 2 ;;
esac
