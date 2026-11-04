#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C8 of 2026-10-27) of
# native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1   (frozen: RUNS="A:-1 B:16 C:32" K=64 LEN=4194296 HOLD=120 IDLE=60, then run R K1=K2=20 RLIM=16)
#   shake: RUNS="A:-1 B:2" K=6 LEN=1048568 HOLD=20 IDLE=5 K1=3 K2=3 RLIM=2 RHOLD1=60 RHOLD2=30 cluster-run.sh shake   (not a reading)
# One node at a time (127.0.0.1, JMX 7199) from clone C (default $W/cassandra-run55); node files $W/node-ntcc, fresh per node, removed at the end.
# Logs: $W/logs/<stem>/cluster-<label>/   (node start/stop adapted from
# harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
STEM=native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous
RUNS=${RUNS:-"A:-1 B:16 C:32"}; K=${K:-64}; LEN=${LEN:-4194296}; HOLD=${HOLD:-120}; IDLE=${IDLE:-60}
K1=${K1:-20}; K2=${K2:-20}; RLIM=${RLIM:-16}; RHOLD1=${RHOLD1:-240}; RHOLD2=${RHOLD2:-120}; DO_R=${DO_R:-1}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run55}
D=$W/node-ntcc; JB=$W/harness-bin-ntcc
L=$W/logs/$STEM/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
PID=""; JP=""
stop_node() {
  [ -z "$PID" ] && return 0
  if kill -0 "$PID" 2>/dev/null; then
    NT stopdaemon >> "$L/commands.log" 2>&1
    local k; for k in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    if kill -0 "$PID" 2>/dev/null; then kill "$PID" 2>/dev/null; sleep 5; kill -9 "$PID" 2>/dev/null; log "node pid $PID killed after 60 s"; fi
  fi
  PID=""; JP=""
  log "node stopped; Cassandra daemon processes left: $(ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon')"
}
kill_holds() { pkill -f "$H/hold_frames.py" 2>/dev/null; sleep 1; pkill -9 -f "$H/hold_frames.py" 2>/dev/null; return 0; }
MAINPID=$$
cleanup() { local me; me=$(exec sh -c 'echo $PPID'); [ "$me" = "$MAINPID" ] || return 0; kill_holds; stop_node; rm -rf "$D"; }
trap cleanup EXIT

log "cluster-run $LABEL RUNS=[$RUNS] K=$K LEN=$LEN HOLD=$HOLD IDLE=$IDLE DO_R=$DO_R K1=$K1 K2=$K2 RLIM=$RLIM RHOLD1=$RHOLD1 RHOLD2=$RHOLD2 clone=$C $(git -C "$C" rev-parse HEAD) hold_sha=$(shasum -a 256 "$H/hold_frames.py" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
mkdir -p "$JB"; javac -d "$JB" "$H/Jmx.java" > "$L/javac.txt" 2>&1 || { log "ABORT: Jmx.java did not compile"; exit 1; }
log "$(python3 --version 2>&1); $(java -version 2>&1 | head -1); ulimit -n $(ulimit -n)"

make_node() { # $1 = limit, $2 = tag
  rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|native_transport_max_concurrent_connections):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (C1 of 2026-10-27) ---
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
native_transport_max_concurrent_connections: $1
YAML
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/$2-yaml.diff"
  return 0
}
start_node() {
  local extra="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G -Dcassandra.netty_use_heap_allocator=true"
  ( cd "$C" && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="$extra" \
    exec bin/cassandra -f > "$D/node-stdout.log" 2>&1 < /dev/null ) &
  PID=$!
  log "started node pid=$PID JVM_EXTRA_OPTS=[$extra]"
}
wait_up() {
  local k
  for k in $(seq 1 150); do
    kill -0 "$PID" 2>/dev/null || { log "node died during start"; return 1; }
    if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = "running" ]; then
      log "node: UN and binary running after ~$((k*2)) s"; return 0; fi
    sleep 2
  done
  log "node not up after 300 s"; return 1
}
est9042() { # $1 = out file -> node-side ESTABLISHED connections on 127.0.0.1.9042
  netstat -an -p tcp > "$1" 2>&1
  awk '$6=="ESTABLISHED" && $4=="127.0.0.1.9042"' "$1" | wc -l | tr -d ' '
}
other() { # $1 = summary.diff file -> committed delta KB of Other
  local l; l=$(grep -E '^-[[:space:]]+Other \(' "$1" | head -1)
  [ -z "$l" ] && { echo "NA"; return; }
  echo "$l" | sed -E 's/.*committed=[0-9]+KB ?([+-][0-9]+KB)?\).*/\1/' | sed -E 's/KB//; s/^$/0/; s/^\+//'
}
rss() { ps -o rss= -p "$JP" | tr -d ' '; }
nlog() { local n; n=$(grep -c 'Exceeded maximum native connection limit' "$D/logs/system.log" 2>/dev/null); echo "${n:-0}"; }
bring_up() { # $1 = tag, $2 = limit
  make_node "$2" "$1"
  start_node; wait_up || { log "ABORT: node did not start"; tail -30 "$D/node-stdout.log" >> "$L/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); log "node java pid=$JP"
  grep -o 'native_transport_max_concurrent_connections=[^;]*; native_transport_max_concurrent_connections_per_ip=[^;]*' "$D/logs/system.log" | head -1 > "$L/$1-config.txt"
  grep -o 'native_transport_idle_timeout=[^;]*' "$D/logs/system.log" | head -1 >> "$L/$1-config.txt"
  grep -o 'native_transport_max_frame_size=[^;]*' "$D/logs/system.log" | head -1 >> "$L/$1-config.txt"
  ps -o command= -p "$JP" | tr ' ' '\n' | grep -E 'NativeMemoryTracking|MaxDirectMemorySize|netty_use_heap_allocator|maxOrder|^-Xmx|^-Xms' > "$L/$1-jvmflags.txt"
  log "config: $(tr '\n' ' ' < "$L/$1-config.txt"); flags: $(tr '\n' ' ' < "$L/$1-jvmflags.txt")"
  log "idle $IDLE s"; sleep "$IDLE"
}
save_node_logs() { cp "$D/node-stdout.log" "$L/$1-node-stdout.log"; cp "$D/logs/system.log" "$L/$1-system.log"; grep 'Exceeded maximum native connection limit' "$D/logs/system.log" > "$L/$1-limit-log-lines.txt"; }

one_run() { # $1 = tag, $2 = limit
  local tag=$1 lim=$2 R=$L/$1; mkdir -p "$R"
  log "=== run $tag: native_transport_max_concurrent_connections=$lim K=$K LEN=$LEN HOLD=$HOLD ==="
  bring_up "$tag" "$lim"
  jcmd "$JP" VM.native_memory baseline > "$R/nmt-baseline.txt" 2>&1
  log "baseline: $(tr '\n' ' ' < "$R/nmt-baseline.txt"); rss_kb=$(rss); est=$(est9042 "$R/netstat-0.txt")"
  local t0; t0=$(date +%s)
  python3 "$H/hold_frames.py" 127.0.0.1 9042 "$K" "$LEN" "$HOLD" > "$R/hold.out" 2> "$R/hold.err" &
  local HP=$!
  log "hold_frames.py pid=$HP launched at t0=$t0"
  local i
  for i in 1 2 3; do
    while [ $(( $(date +%s) - t0 )) -lt $((20 * i)) ]; do sleep 1; done
    [ "$i" = 1 ] && { grep -q '^attempted' "$R/hold.out" || log "STOP CONDITION: no attempted line by t0+20 s (row I)"; }
    local e; e=$(est9042 "$R/netstat-s$i.txt")
    jcmd "$JP" VM.native_memory summary.diff > "$R/nmt-s$i.txt" 2>&1
    log "sample s$i at t0+$(( $(date +%s) - t0 )) s: established=$e other_committed_delta_kb=$(other "$R/nmt-s$i.txt") rss_kb=$(rss) hold.out=[$(cat "$R/hold.out")]"
  done
  wait "$HP"; log "hold_frames.py exited rc=$? at t0+$(( $(date +%s) - t0 )) s: [$(cat "$R/hold.out")] stderr_lines=$(wc -l < "$R/hold.err" | tr -d ' ')"
  sleep 15
  local e; e=$(est9042 "$R/netstat-post.txt")
  jcmd "$JP" VM.native_memory summary.diff > "$R/nmt-post.txt" 2>&1
  log "post at t0+$(( $(date +%s) - t0 )) s: established=$e other_committed_delta_kb=$(other "$R/nmt-post.txt") rss_kb=$(rss)"
  log "limit log lines in run $tag: $(nlog)"
  save_node_logs "$tag"
  stop_node
}

run_r() {
  local tag=R R=$L/R; mkdir -p "$R"
  log "=== run R (informational, C7): start at -1, K1=$K1, set limit $RLIM by JMX, K2=$K2 ==="
  bring_up R -1
  log "established before: $(est9042 "$R/netstat-0.txt")"
  python3 "$H/hold_frames.py" 127.0.0.1 9042 "$K1" "$LEN" "$RHOLD1" > "$R/hold1.out" 2> "$R/hold1.err" &
  local HP1=$! k
  for k in $(seq 1 60); do grep -q '^attempted' "$R/hold1.out" && break; sleep 1; done
  log "hold1: [$(cat "$R/hold1.out")] established=$(est9042 "$R/netstat-1.txt")"
  java -cp "$JB" Jmx 7199 org.apache.cassandra.db:type=StorageProxy NativeTransportMaxConcurrentConnections "$RLIM" > "$R/jmx.txt" 2>&1
  log "jmx: $(tr '\n' ' ' < "$R/jmx.txt")"
  python3 "$H/hold_frames.py" 127.0.0.1 9042 "$K2" "$LEN" "$RHOLD2" > "$R/hold2.out" 2> "$R/hold2.err" &
  local HP2=$!
  for k in $(seq 1 60); do grep -q '^attempted' "$R/hold2.out" && break; sleep 1; done
  log "hold2: [$(cat "$R/hold2.out")]"
  local i; for i in 1 2 3; do sleep 10; log "R sample $i: established=$(est9042 "$R/netstat-s$i.txt")"; done
  log "limit log lines in run R: $(nlog)"
  kill "$HP1" "$HP2" 2>/dev/null; wait "$HP1" "$HP2" 2>/dev/null
  save_node_logs R
  stop_node
}

for spec in $RUNS; do one_run "${spec%%:*}" "${spec#*:}"; done
[ "$DO_R" = 1 ] && run_r
kill_holds; rm -rf "$D"
log "node dir removed; hold_frames left: $(pgrep -f "$H/hold_frames.py" | wc -l | tr -d ' '); daemons left: $(ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon')"
log "cluster-run $LABEL done"
