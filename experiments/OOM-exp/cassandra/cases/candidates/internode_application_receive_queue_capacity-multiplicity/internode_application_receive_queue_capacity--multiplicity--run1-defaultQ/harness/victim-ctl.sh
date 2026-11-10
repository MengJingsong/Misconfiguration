#!/usr/bin/env bash
# C1 OOM-exp victim controller (apt140 / 10.10.1.1). One Cassandra 5.0.9 instance,
# bounded by -XX:MaxDirectMemorySize (Arm D) inside a cgroup v2 scope
# (MemoryMax above the JVM budget, MemorySwapMax=0). concurrent_writes=2 for
# backpressure (disclosed supporting deviation). Instruments the internode
# receive queues (virtual table), reserve, direct memory (NMT), RSS, cgroup.
#   victim-ctl.sh gen <cw>
#   victim-ctl.sh start <directMiB> <xmx> <cgroupMiB>   # writes run meta
#   victim-ctl.sh ready
#   victim-ctl.sh ring
#   victim-ctl.sh qsnap <tag>          # one virtual-table + NMT snapshot
#   victim-ctl.sh monloop <dir> <secs> # bg cheap sampler -> mem.csv
#   victim-ctl.sh qloop   <dir> <secs> # bg queue sampler  -> queue.csv
#   victim-ctl.sh oomcheck             # print OOM/kill evidence
#   victim-ctl.sh stop
set -uo pipefail
BUILD=$HOME/cassandra-b1
ROOT=/mydata/c1
V=$ROOT/victim
IP=10.10.1.1
SEEDS='10.10.1.1:7000,10.10.1.32:7000,10.10.1.48:7000'
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
    -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'c1ring'/" \
    -e "s/^num_tokens: 16/num_tokens: 1/" \
    -e "s/^listen_address: localhost/listen_address: $IP/" \
    -e "s/^rpc_address: localhost/rpc_address: $IP/" \
    -e "s|seeds: \"127.0.0.1:7000\"|seeds: \"$SEEDS\"|" \
    -e "s|^# data_file_directories:|data_file_directories:|" \
    -e "s|^#     - /var/lib/cassandra/data|    - $V/data|" \
    -e "s|^# commitlog_directory: /var/lib/cassandra/commitlog|commitlog_directory: $V/commitlog|" \
    -e "s|^# hints_directory: /var/lib/cassandra/hints|hints_directory: $V/hints|" \
    -e "s|^# saved_caches_directory: /var/lib/cassandra/saved_caches|saved_caches_directory: $V/saved_caches|" \
    -e "s|^key_cache_size:|key_cache_size: 0MiB|" \
    -e "s|^counter_cache_size:|counter_cache_size: 0MiB|" \
    -e "s|^concurrent_writes: 32|concurrent_writes: $cw|" \
    "$y"
  echo "auto_bootstrap: false" >> "$y"
  grep -qE "^concurrent_writes: $cw" "$y" && grep -qE "^listen_address: $IP" "$y" || { log "GEN FAIL"; return 1; }
  log "victim gen ok (concurrent_writes=$cw)"
}

start(){
  local direct=$1 xmx=$2 cg=$3 btm=${4:-}
  local unit="c1victim-$(date +%s)"
  local AGENT=""
  if [ -n "$btm" ] && [ -f "$btm" ]; then
    AGENT=" -Dorg.jboss.byteman.verbose=true -javaagent:$BUILD/build/lib/jars/byteman-4.0.20.jar=script:$btm,listener:true,port:9091,address:127.0.0.1"
  fi
  local REP=""; [ -n "${REPLACE:-}" ] && REP=" -Dcassandra.replace_address_first_boot=$IP -Dcassandra.allow_unsafe_replace=true"
  AGENT="$AGENT$REP"
  # keep system.local (ring identity) across restarts so the victim rejoins without
  # endpoint collision; only clear user data between arms via WIPEDATA=1.
  [ -n "${WIPEDATA:-}" ] && rm -rf "$V"/data/* "$V"/commitlog/* "$V"/hints/* 2>/dev/null
  [ -d "$V/logs" ] && { mkdir -p "$V/logs.prev"; mv "$V"/logs/* "$V/logs.prev/" 2>/dev/null; }
  mkdir -p "$V/logs"
  printf 'unit=%s\ndirect=%s\nxmx=%s\ncgroup=%s\ncw=auto\nstarted=%s\n' "$unit" "$direct" "$xmx" "$cg" "$(date -Is)" > "$META"
  # launcher script (avoids systemd Environment= space-quoting issues)
  cat > "$V/launch-victim.sh" <<EOF
#!/usr/bin/env bash
ulimit -n 100000
cd "$BUILD"
export CASSANDRA_CONF="$V/conf"
export CASSANDRA_LOG_DIR="$V/logs"
export MAX_HEAP_SIZE="$xmx"
export JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=${direct}M -XX:NativeMemoryTracking=summary -Dcassandra.jmx.local.port=7199${AGENT}"
exec "$BUILD/bin/cassandra" -f -p "$V/cass.pid"
EOF
  chmod +x "$V/launch-victim.sh"
  # transient *service* (not --scope): systemd keeps it detached, survives ssh exit.
  systemd-run --user --unit="$unit" \
      -p MemoryMax=${cg}M -p MemorySwapMax=0 -p LimitNOFILE=100000 \
      "$V/launch-victim.sh" >"$V/logs/launch.log" 2>&1
  sleep 5
  local p; p=$(systemctl --user show -p MainPID --value "$unit.service" 2>/dev/null)
  [ -z "$p" ] || [ "$p" = 0 ] && p=$(pgrep -f "cassandra.logdir=$V/logs" | head -1)
  echo "$p" > "$V/cass.pid"
  log "victim start unit=$unit direct=${direct}M xmx=$xmx cgroup=${cg}M pid=$p"
}

ready(){
  local b=$BUILD/bin/nodetool i
  for i in $(seq 1 60); do
    if $b -h 127.0.0.1 -p 7199 statusbinary 2>/dev/null | grep -q running \
       && $b -h 127.0.0.1 -p 7199 status 2>/dev/null | grep -q "^UN.*$IP"; then echo "ready after ${i}x2s"; return 0; fi
    local p; p=$(pidof_victim); { [ -n "$p" ] && kill -0 "$p" 2>/dev/null; } || { echo "victim died"; tail -8 "$V/logs/launch.log"; return 1; }
    sleep 2
  done; echo "ready timeout"; return 1
}
ring(){ $BUILD/bin/nodetool -h 127.0.0.1 -p 7199 status 2>&1; }

qsnap(){
  local tag=$1 p; p=$(pidof_victim)
  local cql="$BUILD/bin/cqlsh $IP -e"
  { echo "## $tag epoch=$(date +%s%3N)";
    $cql "SELECT address,using_bytes,using_reserve_bytes,throttled_count,throttled_nanos,received_count,processed_count,scheduled_count FROM system_views.internode_inbound;" 2>&1 | grep -vE '^$'; } >> "$V/logs/qsnap-$tag.txt"
  if [ -n "$p" ]; then jcmd "$p" VM.native_memory summary 2>/dev/null | grep -A2 -iE 'Internal|Other|Native Memory Tracking|Total:' >> "$V/logs/nmt-$tag.txt"; fi
}

cheap_line(){ # epoch,rssAnonKB,memcur,oom,oom_kill,directReservedB
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
  echo "=== launch.log tail ==="; tail -5 "$V/logs/launch.log" 2>/dev/null
  local cg; cg=$(cgdir); [ -n "$cg" ] && { echo "=== memory.events ==="; cat "$cg/memory.events" 2>/dev/null; echo "memory.current=$(cat "$cg/memory.current" 2>/dev/null) memory.max=$(cat "$cg/memory.max" 2>/dev/null)"; }
  echo "=== dmesg oom ==="; sudo dmesg 2>/dev/null | grep -iE 'oom|killed process|java' | tail -5
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
  gen) gen "$@";; start) start "$@";; ready) ready;; ring) ring;;
  qsnap) qsnap "$@";; monloop) monloop "$@";; qloop) qloop "$@";;
  cheap) cheap_line;; oomcheck) oomcheck;; stop) stop;;
  *) echo "see header"; exit 1;;
esac
