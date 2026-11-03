#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C9 and runbook fix D1 of 2026-10-27) of native_transport_max_frame_size-decode-bytesToDiscard--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1   (frozen: VALUES="16MiB 4MiB 8MiB" K=32 L=8388608 HOLD=120 IDLE=60 DRIFT=50 REL=15)
#   shake: VALUES="4MiB 1MiB" K=4 L=2097152 HOLD=60 IDLE=10 DRIFT=10 cluster-run.sh shake
# One node (127.0.0.1, JMX 7199, observe-only Byteman rules ntfs.btm) from clone C (default $W/cassandra-run54); node files
# $W/node-ntfs, fresh per value, removed at the end. Logs: $W/logs/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/cluster-<label>/
# (node start/stop, trap and logging adapted from harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
VALUES=${VALUES:-16MiB 4MiB 8MiB}; K=${K:-32}; LEN=${L:-8388608}; HOLD=${HOLD:-120}; IDLE=${IDLE:-60}; DRIFT=${DRIFT:-50}; REL=${REL:-15}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run54}
D=$W/node-ntfs
LG=$W/logs/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/cluster-$LABEL; mkdir -p "$LG"; rm -rf "$LG"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LG/commands.log"; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
PID=""; JP=""; HP=""; SP=""
stop_node() {
  [ -z "$PID" ] && return 0
  if kill -0 "$PID" 2>/dev/null; then
    NT stopdaemon >> "$LG/commands.log" 2>&1
    local k; for k in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    if kill -0 "$PID" 2>/dev/null; then kill "$PID" 2>/dev/null; sleep 5; kill -9 "$PID" 2>/dev/null; log "node pid $PID killed after 60 s"; fi
  fi
  PID=""; JP=""
  log "node stopped; Cassandra daemon processes left: $(ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon')"
}
kill_aux() { [ -n "$SP" ] && kill "$SP" 2>/dev/null; SP=""; pkill -f "$H/hold_frames.py" 2>/dev/null; sleep 1; pkill -9 -f "$H/hold_frames.py" 2>/dev/null; return 0; }
MAINPID=$$
cleanup() { local me; me=$(exec sh -c 'echo $PPID'); [ "$me" = "$MAINPID" ] || return 0; kill_aux; stop_node; }  # bash 3.2: act only in the main shell
trap cleanup EXIT

log "cluster-run $LABEL VALUES=[$VALUES] K=$K L=$LEN HOLD=$HOLD IDLE=$IDLE DRIFT=$DRIFT REL=$REL clone=$C $(git -C "$C" rev-parse HEAD) client_sha=$(shasum -a 256 "$H/hold_frames.py" | cut -c1-16) btm_sha=$(shasum -a 256 "$H/ntfs.btm" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
java -cp "$C/build/lib/jars/byteman-4.0.20.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/ntfs.btm" > "$LG/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$LG/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
log "rules type-checked: $(tail -1 "$LG/btm-check.txt"); $(python3 --version 2>&1)"

make_node() { # $1 = value
  rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|native_transport_max_frame_size):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (B3a/B3b, amendments C1/C2 of 2026-10-27) ---
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
native_transport_max_frame_size: $1
YAML
  diff "$C/conf/cassandra.yaml" "$Y" > "$LG/yaml-$1.diff"
  return 0
}
start_node() {
  local extra="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G -Dcassandra.netty_use_heap_allocator=true -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/ntfs.btm"
  ( cd "$C" && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="$extra" \
    exec bin/cassandra -f > "$D/node-stdout.log" 2>&1 < /dev/null ) &
  PID=$!
  log "started node pid=$PID"
}
wait_up() {
  local k
  for k in $(seq 1 150); do
    kill -0 "$PID" 2>/dev/null || { log "node died during start"; return 1; }
    if [ "$(NT statusbinary 2>/dev/null)" = "running" ] && grep -q 'Starting listening for CQL clients' "$D/logs/system.log" 2>/dev/null; then
      log "node: binary running after ~$((k*2)) s"; return 0; fi
    sleep 2
  done
  log "node not up after 300 s"; return 1
}
nmt_diff() { # $1 = out file -> "Other committed delta KiB"
  jcmd "$JP" VM.native_memory summary.diff > "$1" 2>&1
  local line; line=$(grep -E '^-? *Other \(' "$1" | head -1)
  local d; d=$(echo "$line" | sed -n 's/.*committed=[0-9]*KB \([+-][0-9]*\)KB.*/\1/p')
  echo "${d:-0}"
}
rss() { ps -o rss= -p "$JP" | tr -d ' '; }
amem() { # $1 = out file: one NTFMEM line triggered by nodetool version
  local before after k; before=$(grep -c '^NTFMEM ' "$D/node-stdout.log" 2>/dev/null); before=${before:-0}
  NT version > /dev/null 2>&1
  for k in $(seq 1 20); do after=$(grep -c '^NTFMEM ' "$D/node-stdout.log" 2>/dev/null); [ "${after:-0}" -gt "$before" ] && break; sleep 0.5; done
  grep '^NTFMEM ' "$D/node-stdout.log" | tail -1 > "$1"
  cat "$1"
}
cnt() { local n; n=$(grep -c "^$1 " "$D/node-stdout.log" 2>/dev/null); echo "${n:-0}"; }

node_run() { # $1 = value
  local v=$1 R=$LG/$1; mkdir -p "$R"
  log "=== node: native_transport_max_frame_size=$v ==="
  make_node "$v"
  start_node; wait_up || { log "ABORT: node did not start (run invalid)"; tail -30 "$D/node-stdout.log" >> "$LG/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); log "node java pid=$JP"
  grep -o 'native_transport_max_frame_size=[^;]*' "$D/logs/system.log" | head -1 > "$R/config.txt"
  grep -o 'native_transport_idle_timeout=[^;]*' "$D/logs/system.log" | head -1 >> "$R/config.txt"
  ps -o command= -p "$JP" | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|NativeMemoryTracking|javaagent|Xmx|netty_use_heap_allocator|maxOrder' > "$R/jvm-flags.txt"
  log "config: $(tr '\n' ' ' < "$R/config.txt"); flags: $(tr '\n' ' ' < "$R/jvm-flags.txt")"
  ( while kill -0 "$JP" 2>/dev/null; do echo "$(date +%s) $(ps -o rss= -p "$JP" | tr -d ' ')"; sleep 5; done ) > "$R/rss.txt" 2>/dev/null &
  SP=$!
  log "idle $IDLE s"; sleep "$IDLE"
  jcmd "$JP" VM.native_memory baseline > "$R/nmt-baseline.txt" 2>&1
  log "NMT baseline: $(tr '\n' ' ' < "$R/nmt-baseline.txt"); RSS KiB $(rss)"
  log "base mem: $(amem "$R/ntfmem-base.txt")"
  local d0c=$(cnt NTFDISCARD) f0c=$(cnt NTFFAIL)
  sleep "$DRIFT"
  log "D0 (drift, Other committed delta KiB): $(nmt_diff "$R/nmt-D0.txt"); RSS KiB $(rss)"
  python3 "$H/hold_frames.py" 127.0.0.1 9042 "$K" "$LEN" "$HOLD" > "$R/client.out" 2> "$R/client.err" &
  HP=$!
  local k ok=0
  for k in $(seq 1 240); do grep -q '^holding' "$R/client.out" 2>/dev/null && { ok=1; break; }; sleep 0.5; done
  log "client: [$(grep '^holding' "$R/client.out")] after ~$((k/2)) s"
  [ "$ok" = 1 ] || { log "STOP CONDITION: client printed no holding line within 120 s (run invalid)"; exit 1; }
  sleep 10
  local i
  for i in 1 2 3; do
    log "S$i (Other committed delta KiB): $(nmt_diff "$R/nmt-S$i.txt"); RSS KiB $(rss); $(amem "$R/ntfmem-S$i.txt"); NTFDISCARD so far $(( $(cnt NTFDISCARD) - d0c ))"
    [ "$i" -lt 3 ] && sleep 20
  done
  log "waiting for the client to exit"
  wait "$HP"; log "client rc=$? ; responses: $(grep -c '^resp ' "$R/client.out"); last: $(tail -1 "$R/client.out")"; HP=""
  sleep "$REL"
  log "R (release, Other committed delta KiB): $(nmt_diff "$R/nmt-R.txt"); RSS KiB $(rss); $(amem "$R/ntfmem-R.txt")"
  log "NTFDISCARD in run: $(( $(cnt NTFDISCARD) - d0c )); NTFFAIL in run: $(( $(cnt NTFFAIL) - f0c )); 'Request is too big' in system.log: $(grep -c 'Request is too big' "$D/logs/system.log")"
  kill "$SP" 2>/dev/null; SP=""
  cp "$D/node-stdout.log" "$R/node-stdout.log"; cp "$D/logs/system.log" "$R/system.log"
  grep -E '^NTF(DISCARD|FAIL|MEM) ' "$D/node-stdout.log" > "$R/btm-lines.txt"
  stop_node
}

for v in $VALUES; do node_run "$v"; done
rm -rf "$D"
log "node files removed; Cassandra daemon left: $(ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon'); client left: $(pgrep -f "$H/hold_frames.py" | wc -l | tr -d ' '); :9042 listeners: $(lsof -nP -iTCP:9042 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' '); clone status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
log "cluster-run $LABEL done"
