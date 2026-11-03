#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C8 of 2026-10-27) of
# native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1    (frozen: RUNS="A:-1 B:16 C:32" K1=64 K2=16 LEN=4194296 HOLD1=120 HOLD2=90 IDLE=60)
#   shake: RUNS="A:-1 B:2" K1=6 K2=3 LEN=1048568 IDLE=5 cluster-run.sh shake    (not a reading)
# One node at a time (127.0.0.1, JMX 7199) from clone C (default $W/cassandra-run56); node files $W/node-ntpip, fresh per node,
# removed at the end. Script 1 connects from 127.0.0.1, script 2 from source 127.0.0.2 (C2).
# Logs: $W/logs/<stem>/cluster-<label>/  (node start/stop and logging skeleton adapted from
# harness/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
STEM=native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous
RUNS=${RUNS:-"A:-1 B:16 C:32"}; K1=${K1:-64}; K2=${K2:-16}; LEN=${LEN:-4194296}; HOLD1=${HOLD1:-120}; HOLD2=${HOLD2:-90}; IDLE=${IDLE:-60}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run56}
D=$W/node-ntpip
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

log "cluster-run $LABEL RUNS=[$RUNS] K1=$K1 K2=$K2 LEN=$LEN HOLD1=$HOLD1 HOLD2=$HOLD2 IDLE=$IDLE clone=$C $(git -C "$C" rev-parse HEAD) hold_sha=$(shasum -a 256 "$H/hold_frames.py" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
ifconfig lo0 | grep -q 'inet 127.0.0.2 ' || { log "ABORT: loopback alias 127.0.0.2 missing"; exit 1; }
log "$(python3 --version 2>&1); $(java -version 2>&1 | head -1); ulimit -n $(ulimit -n)"

make_node() { # $1 = per-IP limit, $2 = tag
  rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|native_transport_max_concurrent_connections|native_transport_max_concurrent_connections_per_ip):' "$C/conf/cassandra.yaml" > "$Y"
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
native_transport_max_concurrent_connections: -1
native_transport_max_concurrent_connections_per_ip: $1
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
est() { # $1 = out file -> "n1 n2": node-side ESTABLISHED connections on 127.0.0.1.9042 from 127.0.0.1 and from 127.0.0.2
  netstat -an -p tcp > "$1" 2>&1
  local a b
  a=$(awk '$6=="ESTABLISHED" && $4=="127.0.0.1.9042" && $5 ~ /^127\.0\.0\.1\.[0-9]+$/' "$1" | wc -l | tr -d ' ')
  b=$(awk '$6=="ESTABLISHED" && $4=="127.0.0.1.9042" && $5 ~ /^127\.0\.0\.2\.[0-9]+$/' "$1" | wc -l | tr -d ' ')
  echo "$a $b"
}
other() { # $1 = summary.diff file -> committed delta KB of Other
  local l; l=$(grep -E '^-[[:space:]]+Other \(' "$1" | head -1)
  [ -z "$l" ] && { echo "NA"; return; }
  echo "$l" | sed -E 's/.*committed=[0-9]+KB ?([+-][0-9]+KB)?\).*/\1/' | sed -E 's/KB//; s/^$/0/; s/^\+//'
}
rss() { ps -o rss= -p "$JP" | tr -d ' '; }
gip() { local n; n=$(grep -c 'Exceeded maximum native connection limit per ip' "$D/logs/system.log" 2>/dev/null); echo "${n:-0}"; }
gglob() { local n; n=$(grep -c 'see native_transport_max_concurrent_connections in cassandra.yaml' "$D/logs/system.log" 2>/dev/null); echo "${n:-0}"; }
bring_up() { # $1 = tag, $2 = limit
  make_node "$2" "$1"
  start_node; wait_up || { log "ABORT: node did not start"; tail -30 "$D/node-stdout.log" >> "$L/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); log "node java pid=$JP"
  grep -o 'native_transport_max_concurrent_connections=[^;]*; native_transport_max_concurrent_connections_per_ip=[^;]*' "$D/logs/system.log" | head -1 > "$L/$1-config.txt"
  grep -o 'native_transport_idle_timeout=[^;]*' "$D/logs/system.log" | head -1 >> "$L/$1-config.txt"
  grep -o 'native_transport_max_frame_size=[^;]*' "$D/logs/system.log" | head -1 >> "$L/$1-config.txt"
  grep -o '; rpc_address=[^;]*' "$D/logs/system.log" | head -1 >> "$L/$1-config.txt"
  ps -o command= -p "$JP" | tr ' ' '\n' | grep -E 'NativeMemoryTracking|MaxDirectMemorySize|netty_use_heap_allocator|maxOrder|^-Xmx|^-Xms' > "$L/$1-jvmflags.txt"
  log "config: $(tr '\n' ' ' < "$L/$1-config.txt"); flags: $(tr '\n' ' ' < "$L/$1-jvmflags.txt")"
  log "idle $IDLE s"; sleep "$IDLE"
}
save_node_logs() { cp "$D/node-stdout.log" "$L/$1-node-stdout.log"; cp "$D/logs/system.log" "$L/$1-system.log"; grep 'Exceeded maximum native connection limit' "$D/logs/system.log" > "$L/$1-limit-log-lines.txt"; }
until_t() { while [ $(( $(date +%s) - T0 )) -lt "$1" ]; do sleep 1; done; }
sample() { # $1 = run dir, $2 = sample name
  local e; e=$(est "$1/netstat-$2.txt")
  jcmd "$JP" VM.native_memory summary.diff > "$1/nmt-$2.txt" 2>&1
  log "sample $2 at t0+$(( $(date +%s) - T0 )) s: est_127.0.0.1=${e% *} est_127.0.0.2=${e#* } other_committed_delta_kb=$(other "$1/nmt-$2.txt") rss_kb=$(rss)"
}

one_run() { # $1 = tag, $2 = per-IP limit
  local tag=$1 lim=$2 R=$L/$1; mkdir -p "$R"
  log "=== run $tag: native_transport_max_concurrent_connections_per_ip=$lim K1=$K1 K2=$K2 LEN=$LEN ==="
  bring_up "$tag" "$lim"
  jcmd "$JP" VM.native_memory baseline > "$R/nmt-baseline.txt" 2>&1
  local e0; e0=$(est "$R/netstat-0.txt")
  log "baseline: $(tr '\n' ' ' < "$R/nmt-baseline.txt"); rss_kb=$(rss); est=[$e0]"
  T0=$(date +%s)
  python3 "$H/hold_frames.py" 127.0.0.1 9042 "$K1" "$LEN" "$HOLD1" > "$R/hold1.out" 2> "$R/hold1.err" &
  local HP1=$!
  log "script 1 (from 127.0.0.1) pid=$HP1 launched at t0=$T0"
  until_t 20; grep -q '^attempted' "$R/hold1.out" || log "STOP CONDITION: script 1 printed no attempted line by t0+20 s (row I)"
  sample "$R" s1; until_t 25; sample "$R" s2; until_t 30; sample "$R" s3
  until_t 35
  python3 "$H/hold_frames.py" 127.0.0.1 9042 "$K2" "$LEN" "$HOLD2" 127.0.0.2 > "$R/hold2.out" 2> "$R/hold2.err" &
  local HP2=$!
  log "script 2 (from 127.0.0.2) pid=$HP2 launched at t0+$(( $(date +%s) - T0 )) s; script 1: [$(cat "$R/hold1.out")]"
  until_t 55; grep -q '^attempted' "$R/hold2.out" || log "STOP CONDITION: script 2 printed no attempted line by t0+55 s (row I)"
  sample "$R" s4; until_t 60; sample "$R" s5; until_t 65; sample "$R" s6
  wait "$HP1"; log "script 1 exited rc=$? at t0+$(( $(date +%s) - T0 )) s: [$(cat "$R/hold1.out")] stderr_lines=$(wc -l < "$R/hold1.err" | tr -d ' ')"
  wait "$HP2"; log "script 2 exited rc=$? at t0+$(( $(date +%s) - T0 )) s: [$(cat "$R/hold2.out")] stderr_lines=$(wc -l < "$R/hold2.err" | tr -d ' ')"
  sleep 15
  sample "$R" post
  log "log lines in run $tag: per_ip=$(gip) global=$(gglob)"
  save_node_logs "$tag"
  stop_node
}

for spec in $RUNS; do one_run "${spec%%:*}" "${spec#*:}"; done
kill_holds; rm -rf "$D"
log "node dir removed; hold_frames left: $(pgrep -f "$H/hold_frames.py" | wc -l | tr -d ' '); daemons left: $(ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon')"
log "cluster-run $LABEL done"
