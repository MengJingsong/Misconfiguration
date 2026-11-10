#!/usr/bin/env bash
# C1-reopen victim controller (apt140 / 10.10.1.1). Design v2: victim is the ONLY
# replica (dc=v), GossipingPropertyFileSnitch, explicit initial_token. Per-arm Q is
# set by `setq` (no identity wipe). E/G pinned to defaults (128/512 MiB). Budget via
# -XX:MaxDirectMemorySize inside a cgroup v2 scope (MemoryMax>budget, MemorySwapMax=0).
#   victim-ctl2.sh gen <cw>              # ONCE: identity, dc=v, token, snitch, E/G, Q=4
#   victim-ctl2.sh setq <MiB>            # change receive-queue Q only (no wipe)
#   victim-ctl2.sh start <directMiB> <xmx> <cgroupMiB> [btmfile]
#   victim-ctl2.sh ready | ring | cfgdump | stop
#   victim-ctl2.sh qsnap <tag> | monloop <dir> <secs> | qloop <dir> <secs> | oomcheck
set -uo pipefail
BUILD=$HOME/cassandra-b1
ROOT=/mydata/c1r
V=$ROOT/victim
IP=10.10.1.1
TOKEN=-9223372036854775808
SEEDS='10.10.1.1:7000,10.10.1.32:7000'
META=$V/run.meta
log(){ echo "[$(date '+%T')] $*"; }
pidof_victim(){ cat "$V/cass.pid" 2>/dev/null; }
cgdir(){ local p; p=$(pidof_victim); [ -n "$p" ] || return 1
  local rel; rel=$(cut -d: -f3 /proc/"$p"/cgroup 2>/dev/null); [ -n "$rel" ] && echo "/sys/fs/cgroup$rel"; }

gen(){
  local cw=${1:-2}
  rm -rf "$V"; mkdir -p "$V"/{data,commitlog,hints,saved_caches,logs}
  cp -r "$BUILD/conf" "$V/conf"
  local y=$V/conf/cassandra.yaml
  sed -i \
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c1rring'/" \
    -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $IP/" \
    -e "s/^rpc_address: localhost/rpc_address: $IP/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"$SEEDS\"|" \
    -e "s/^endpoint_snitch: SimpleSnitch/endpoint_snitch: GossipingPropertyFileSnitch/" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $V/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $V/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $V/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $V/saved_caches|" \
    -e "s|^key_cache_size:|key_cache_size: 0MiB|" \
    -e "s|^counter_cache_size:|counter_cache_size: 0MiB|" \
    -e "s|^concurrent_writes: 32|concurrent_writes: $cw|" \
    -e "s|^# internode_application_receive_queue_capacity: 4MiB|internode_application_receive_queue_capacity: 4MiB|" \
    -e "s|^# internode_application_receive_queue_reserve_endpoint_capacity: 128MiB|internode_application_receive_queue_reserve_endpoint_capacity: 128MiB|" \
    -e "s|^# internode_application_receive_queue_reserve_global_capacity: 512MiB|internode_application_receive_queue_reserve_global_capacity: 512MiB|" \
    "$y"
  echo "auto_bootstrap: false" >> "$y"
  echo "initial_token: $TOKEN" >> "$y"
  # snitch dc/rack: victim datacenter = v
  printf 'dc=v\nrack=r1\n' > "$V/conf/cassandra-rackdc.properties"
  grep -qE "^concurrent_writes: $cw" "$y" && grep -qE "^listen_address: $IP" "$y" \
    && grep -qE "^endpoint_snitch: GossipingPropertyFileSnitch" "$y" \
    && grep -qE "^internode_application_receive_queue_capacity: 4MiB" "$y" || { log "GEN FAIL"; return 1; }
  log "victim gen ok (cw=$cw dc=v token=$TOKEN Q=4MiB E=128 G=512)"
}

setq(){
  local q=$1 y=$V/conf/cassandra.yaml
  sed -i -E "s|^internode_application_receive_queue_capacity: .*|internode_application_receive_queue_capacity: ${q}MiB|" "$y"
  grep -qE "^internode_application_receive_queue_capacity: ${q}MiB" "$y" && log "setq Q=${q}MiB" || { log "SETQ FAIL"; return 1; }
}

start(){
  local direct=$1 xmx=$2 cg=$3 btm=${4:-}
  local unit="c1rvictim-$(date +%s)"
  local AGENT=""
  if [ -n "$btm" ] && [ -f "$btm" ]; then
    AGENT=" -Dorg.jboss.byteman.verbose=true -javaagent:$BUILD/build/lib/jars/byteman-4.0.20.jar=script:$btm,listener:true,port:9091,address:127.0.0.1"
  fi
  [ -d "$V/logs" ] && { mkdir -p "$V/logs.prev"; mv "$V"/logs/* "$V/logs.prev/" 2>/dev/null; }
  mkdir -p "$V/logs"
  printf 'unit=%s\ndirect=%s\nxmx=%s\ncgroup=%s\nstarted=%s\n' "$unit" "$direct" "$xmx" "$cg" "$(date -Is)" > "$META"
  cat > "$V/launch-victim.sh" <<EOF
#!/usr/bin/env bash
ulimit -n 100000
cd "$BUILD"
export CASSANDRA_CONF="$V/conf"
export CASSANDRA_LOG_DIR="$V/logs"
export MAX_HEAP_SIZE="$xmx"
export HEAP_NEWSIZE="512M"
export JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=${direct}M -XX:NativeMemoryTracking=summary -Dcassandra.jmx.local.port=7199${AGENT}"
exec "$BUILD/bin/cassandra" -f -p "$V/cass.pid"
EOF
  chmod +x "$V/launch-victim.sh"
  systemd-run --user --unit="$unit" \
      -p MemoryMax=${cg}M -p MemorySwapMax=0 -p LimitNOFILE=100000 \
      "$V/launch-victim.sh" >"$V/logs/launch.log" 2>&1
  sleep 5
  local p; p=$(systemctl --user show -p MainPID --value "$unit.service" 2>/dev/null)
  [ -z "$p" ] || [ "$p" = 0 ] && p=$(pgrep -f "cassandra.logdir=$V/logs" | head -1)
  echo "$p" > "$V/cass.pid"
  log "victim start unit=$unit direct=${direct}M xmx=$xmx cgroup=${cg}M pid=$p btm=${btm:-none}"
}

ready(){
  local b="$BUILD/bin/nodetool"
  for i in $(seq 1 90); do
    if $b -h 127.0.0.1 -p 7199 statusbinary 2>/dev/null | grep -q running \
       && $b -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -q "^UN.*$IP"; then echo "ready after $((i*2))s"; return 0; fi
    local p; p=$(pidof_victim); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; } || { echo "victim died"; tail -12 "$V/logs/launch.log"; grep -nE 'OutOfMemory|Direct buffer|ERROR' "$V/logs/system.log" 2>/dev/null | tail -5; return 1; }
    sleep 2
  done; echo "ready timeout"; return 1
}
ring(){ $BUILD/bin/nodetool -h 127.0.0.1 -p 7199 status 2>&1; }
cfgdump(){ grep -nE 'OnConfigChange|Node configuration' "$V/logs/system.log" 2>/dev/null | head;
  grep -oE 'internode_application_receive_queue_capacity=[0-9]+|internode_application_receive_queue_reserve_endpoint_capacity=[0-9]+|internode_application_receive_queue_reserve_global_capacity=[0-9]+' "$V/logs/system.log" 2>/dev/null | sort -u; }

qsnap(){
  local tag=$1 p; p=$(pidof_victim)
  local cql="$BUILD/bin/cqlsh $IP -e"
  { echo "## $tag epoch=$(date +%s%3N)";
    $cql "SELECT address,using_bytes,using_reserve_bytes,throttled_count,throttled_nanos,received_count,processed_count,scheduled_count FROM system_views.internode_inbound;" 2>&1 | grep -vE '^$'; } >> "$V/logs/qsnap-$tag.txt"
  if [ -n "$p" ]; then jcmd "$p" VM.native_memory summary 2>/dev/null >> "$V/logs/nmt-$tag.txt"; fi
}

cheap_line(){
  local p; p=$(pidof_victim); local e; e=$(date +%s%3N)
  local ra=NA mc=NA oom=NA ok=NA
  [ -r "/proc/$p/status" ] && ra=$(awk '/^RssAnon:/{print $2}' "/proc/$p/status")
  local cg; cg=$(cgdir)
  if [ -n "$cg" ] && [ -r "$cg/memory.current" ]; then mc=$(cat "$cg/memory.current"); oom=$(awk '/^oom /{print $2}' "$cg/memory.events"); ok=$(awk '/^oom_kill /{print $2}' "$cg/memory.events"); fi
  echo "$e,$ra,$mc,$oom,$ok"
}
monloop(){ local dir=$1 secs=$2 end=$((SECONDS+secs)); echo "epoch_ms,rssAnonKB,mem_current,oom,oom_kill" > "$dir/mem.csv"
  while [ $SECONDS -lt $end ]; do cheap_line >> "$dir/mem.csv"; sleep 1; done; }
qloop(){ local dir=$1 secs=$2 end=$((SECONDS+secs)); local cql="$BUILD/bin/cqlsh $IP -e"
  echo "# queue samples" > "$dir/queue.csv"
  while [ $SECONDS -lt $end ]; do
    echo "@ $(date +%s%3N)" >> "$dir/queue.csv"
    $cql "SELECT address,using_bytes,using_reserve_bytes,throttled_count,received_count,processed_count FROM system_views.internode_inbound;" 2>&1 | grep -E '10\.10\.1\.|using_bytes|rows' >> "$dir/queue.csv"
    sleep 2
  done; }

oomcheck(){
  echo "=== system.log OOM/error ==="; grep -nE 'OutOfMemoryError|Direct buffer memory|forceHeapSpaceOom|Out of memory|Killing' "$V/logs/system.log" 2>/dev/null | head -20
  echo "=== launch.log tail ==="; tail -6 "$V/logs/launch.log" 2>/dev/null
  local cg; cg=$(cgdir); [ -n "$cg" ] && { echo "=== memory.events ==="; cat "$cg/memory.events" 2>/dev/null; echo "memory.current=$(cat "$cg/memory.current" 2>/dev/null) memory.max=$(cat "$cg/memory.max" 2>/dev/null)"; }
  local p; p=$(pidof_victim); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo "victim ALIVE pid=$p"; } || echo "victim NOT running"
}

stop(){
  local unit; unit=$(awk -F= '/^unit=/{print $2}' "$META" 2>/dev/null)
  [ -n "$unit" ] && systemctl --user stop "$unit.service" 2>/dev/null
  sleep 3; pkill -f "cassandra.logdir=$V/logs" 2>/dev/null
  log "victim stop done (unit=$unit)"
}

cmd=${1:-}; shift || true
case "$cmd" in
  gen) gen "$@";; setq) setq "$@";; start) start "$@";; ready) ready;; ring) ring;; cfgdump) cfgdump;;
  qsnap) qsnap "$@";; monloop) monloop "$@";; qloop) qloop "$@";;
  cheap) cheap_line;; oomcheck) oomcheck;; stop) stop;;
  *) echo "see header"; exit 1;;
esac
