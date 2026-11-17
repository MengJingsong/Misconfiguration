#!/usr/bin/env bash
# Stage-4 recheck run (2026-11-17) of native_transport_max_frame_size-decode-bytesToDiscard--autonomous:
# the case file's section "Stage-4 design for the recheck claim (2026-11-17)". Runs on pc84, from an ssh session kept open.
# usage: run.sh <label>
#   r1:    run.sh r1     (frozen: ARMS="CTRL:complete:512 H64:partial:64 H256:partial:256 H512:partial:512" L=16777207 HOLD=90 IDLE=60 DRIFT=50 REL=15)
#   shake: ARMS="CTRL:complete:8 H8:partial:8" HOLD=30 IDLE=15 DRIFT=10 run.sh shake
# One node (127.0.0.1) per arm from the run copy C (default /mydata/s4/ntfs-rc), shipped conf with addresses/directories overridden,
# in a systemd user scope (MemoryMax=24G, MemorySwapMax=0); default pooled allocator; observe-only Byteman rules ntfr.btm.
# Logs: $C/logs/<label>/. Node start/stop, trap and NMT parsing adapted from
# harness/native_transport_max_frame_size-decode-bytesToDiscard--autonomous/cluster-run.sh.
set -uo pipefail
LABEL=$1
ARMS=${ARMS:-CTRL:complete:512 H64:partial:64 H256:partial:256 H512:partial:512}
LEN=${L:-16777207}; HOLD=${HOLD:-90}; IDLE=${IDLE:-60}; DRIFT=${DRIFT:-50}; REL=${REL:-15}
MEMMAX=${MEMMAX:-24G}; HEAP=${HEAP:-4G}; DIRECT=${DIRECT:-15872M}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-/mydata/s4/ntfs-rc}
LG=$C/logs/$LABEL; mkdir -p "$LG"; rm -rf "${LG:?}"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T') $(date +%s%3N)] $*" | tee -a "$LG/commands.log"; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
PID=""; JP=""; HP=""; D=""; CG=""
ndaemons() { ps -eo cmd | grep -c '[C]assandraDaemon'; }
stop_node() {
  [ -z "$JP" ] && return 0
  if kill -0 "$JP" 2>/dev/null; then
    NT stopdaemon >> "$LG/commands.log" 2>&1
    local k; for k in $(seq 1 60); do kill -0 "$JP" 2>/dev/null || break; sleep 1; done
    if kill -0 "$JP" 2>/dev/null; then kill "$JP" 2>/dev/null; sleep 5; kill -9 "$JP" 2>/dev/null; log "node pid $JP killed after 60 s"; fi
  fi
  wait "$PID" 2>/dev/null
  PID=""; JP=""
  log "node stopped; Cassandra daemon processes left: $(ndaemons)"
}
kill_client() { [ -n "$HP" ] && kill "$HP" 2>/dev/null; HP=""; pkill -f "$H/hold_prelogin.py" 2>/dev/null; return 0; }
cleanup() { kill_client; stop_node; }
trap cleanup EXIT

log "run $LABEL ARMS=[$ARMS] L=$LEN HOLD=$HOLD IDLE=$IDLE DRIFT=$DRIFT REL=$REL MEMMAX=$MEMMAX HEAP=$HEAP DIRECT=$DIRECT C=$C host=$(hostname -s)"
log "sha256: run.sh $(sha256sum "$0" | cut -c1-16) client $(sha256sum "$H/hold_prelogin.py" | cut -c1-16) btm $(sha256sum "$H/ntfr.btm" | cut -c1-16) probe $(sha256sum "$H/probe/ntfr/Probe.java" | cut -c1-16)"
log "$(uname -r); $(java -version 2>&1 | head -1); $(python3 --version 2>&1); $(nproc) cores; $(free -g | awk '/Mem:/{print $2" GiB RAM"}'); swap $(swapon --show=SIZE --noheadings | tr '\n' ' ')"
[ "$(ndaemons)" = 0 ] || { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do ss -ltnH "sport = :$p" | grep -q . && { log "ABORT: port $p busy"; exit 1; }; done
J=$C/build/lib/jars
PJ=$C/ntfr-probe; rm -rf "$PJ"; mkdir -p "$PJ/classes"
javac -cp "$J/netty-buffer-4.1.130.Final.jar:$J/netty-common-4.1.130.Final.jar" -d "$PJ/classes" "$H/probe/ntfr/Probe.java" > "$LG/probe-javac.txt" 2>&1 \
  && jar cf "$PJ/ntfr-probe.jar" -C "$PJ/classes" . || { log "ABORT: probe helper did not compile"; exit 1; }
log "probe helper built: $PJ/ntfr-probe.jar ($(sha256sum "$H/probe/ntfr/Probe.java" | cut -c1-16))"
java -cp "$J/byteman-4.0.20.jar:$C/build/classes/main:$J/*:$PJ/ntfr-probe.jar" org.jboss.byteman.check.TestScript "$H/ntfr.btm" > "$LG/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$LG/btm-check.txt" || { log "ABORT: Byteman rule check failed"; cat "$LG/btm-check.txt" >> "$LG/commands.log"; exit 1; }
log "rules type-checked: $(grep 'TestScript:' "$LG/btm-check.txt" | tail -1)"

make_node() { # $1 = arm
  D=$C/node-$1; rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 recheck overrides (addresses and directories only; every limit at its shipped default) ---
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
YAML
  diff "$C/conf/cassandra.yaml" "$Y" > "$LG/yaml-$1.diff"
  return 0
}
start_node() { # $1 = arm
  local extra="-XX:NativeMemoryTracking=summary -javaagent:$J/byteman-4.0.20.jar=script:$H/ntfr.btm,sys:$PJ/ntfr-probe.jar"
  local unit="ntfs-rc-$LABEL-$1-$(date +%s)"
  ( cd "$C" && ulimit -n 100000 && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=$HEAP MAX_DIRECT_MEMORY_SIZE=$DIRECT JVM_EXTRA_OPTS="$extra" \
    exec systemd-run --user --scope --unit="$unit" -p MemoryMax=$MEMMAX -p MemorySwapMax=0 bin/cassandra -f > "$D/node-stdout.log" 2>&1 < /dev/null ) &
  PID=$!
  log "started scope $unit, launcher pid=$PID"
}
wait_up() {
  local k
  for k in $(seq 1 150); do
    [ -z "$JP" ] && JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1)
    kill -0 "$PID" 2>/dev/null || { log "node died during start"; return 1; }
    if [ "$(NT statusbinary 2>/dev/null)" = "running" ] && grep -q 'Starting listening for CQL clients' "$D/logs/system.log" 2>/dev/null; then
      log "node: binary running after ~$((k*2)) s"; return 0; fi
    sleep 2
  done
  log "node not up after 300 s"; return 1
}
nmt_other() { # $1 = out file -> Other committed delta KiB
  jcmd "$JP" VM.native_memory summary.diff > "$1" 2>&1
  local line d; line=$(grep -E '^-? *Other \(' "$1" | head -1)
  d=$(echo "$line" | sed -n 's/.*committed=[0-9]*KB \([+-][0-9]*\)KB.*/\1/p')
  echo "${d:-0}"
}
amem() { # one NTFMEM line triggered by nodetool version
  local before after k; before=$(grep -c '^NTFMEM ' "$D/node-stdout.log" 2>/dev/null); before=${before:-0}
  NT version > /dev/null 2>&1
  for k in $(seq 1 40); do after=$(grep -c '^NTFMEM ' "$D/node-stdout.log" 2>/dev/null); [ "${after:-0}" -gt "$before" ] && break; sleep 0.5; done
  grep '^NTFMEM ' "$D/node-stdout.log" | tail -1
}
sample() { # $1 = arm dir, $2 = sample name (base D0 S1 S2 S3 R)
  local R=$1 f=$1/$2.txt
  if [ "$2" = base ]; then jcmd "$JP" VM.native_memory baseline > "$R/nmt-base.txt" 2>&1; jcmd "$JP" VM.native_memory summary > "$R/nmt-base-summary.txt" 2>&1; local o=0
  else local o; o=$(nmt_other "$R/nmt-$2.txt"); fi
  { echo "sample=$2"; echo "t_ms=$(date +%s%3N)"; echo "memory.current=$(cat "$CG/memory.current")"
    sed 's/^\([a-z_]*\) /memory.events.\1=/' "$CG/memory.events"
    echo "rss_kib=$(awk '/VmRSS/{print $2}' /proc/$JP/status)"; echo "nmt_other_delta_kib=$o"; amem; } > "$f"
  log "$2: $(tr '\n' ' ' < "$f")"
}
cnt() { local n; n=$(grep -c "^$1 " "$D/node-stdout.log" 2>/dev/null); echo "${n:-0}"; }

arm_run() { # $1 = name:mode:k
  local name mode k; IFS=: read -r name mode k <<< "$1"
  local R=$LG/$name; mkdir -p "$R"
  log "=== arm $name: mode=$mode k=$k L=$LEN ==="
  make_node "$name"; start_node "$name"
  wait_up || { log "ABORT: node did not start (run invalid)"; tail -40 "$D/node-stdout.log" >> "$LG/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1)
  CG=/sys/fs/cgroup$(cut -d: -f3 /proc/$JP/cgroup)
  log "node java pid=$JP cgroup=$CG memory.max=$(cat $CG/memory.max) memory.swap.max=$(cat $CG/memory.swap.max) nofile=$(awk '/Max open files/{print $4}' /proc/$JP/limits)"
  grep -o 'Node configuration:\[.*' "$D/logs/system.log" | head -1 | tr ';' '\n' | grep -E '^ ?native_transport_(max_frame_size|max_concurrent_connections|max_concurrent_connections_per_ip|idle_timeout|max_request_data_in_flight|max_request_data_in_flight_per_ip|receive_queue_capacity)=' | sed 's/^ //' > "$R/config.txt"
  jcmd "$JP" VM.flags 2>/dev/null | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|MaxHeapSize|NativeMemoryTracking' >> "$R/config.txt"
  ps -o args= -p "$JP" | tr ' ' '\n' | grep -E 'MaxDirectMemorySize|maxOrder|netty_use_heap_allocator|javaagent|Xmx|Xms' > "$R/jvm-args.txt"
  echo "scope_memory.max=$(cat $CG/memory.max)" >> "$R/config.txt"; echo "scope_memory.swap.max=$(cat $CG/memory.swap.max)" >> "$R/config.txt"
  log "config: $(tr '\n' ' ' < "$R/config.txt"); args: $(tr '\n' ' ' < "$R/jvm-args.txt")"
  log "idle $IDLE s"; sleep "$IDLE"
  sample "$R" base
  sleep "$DRIFT"
  sample "$R" D0
  python3 "$H/hold_prelogin.py" "$mode" 127.0.0.1 9042 "$k" "$LEN" "$HOLD" > "$R/client.out" 2> "$R/client.err" &
  HP=$!
  local i ok=0
  for i in $(seq 1 600); do grep -q '^holding' "$R/client.out" 2>/dev/null && { ok=1; break; }; kill -0 "$HP" 2>/dev/null || break; sleep 0.5; done
  log "client: [$(grep '^holding' "$R/client.out")]; connect errors $(grep -c '^connect ' "$R/client.out"); ctrl responses $(grep -c '^ctrlresp .*opcode=6' "$R/client.out")"
  [ "$ok" = 1 ] || { log "STOP CONDITION: client printed no holding line within 300 s"; kill_client; tail -20 "$R/client.out" >> "$LG/commands.log"; exit 1; }
  sleep 10; sample "$R" S1
  sleep 20; sample "$R" S2
  sleep 20; sample "$R" S3
  log "waiting for the client to exit"
  wait "$HP"; log "client rc=$?; $(grep '^alive' "$R/client.out"); SUPPORTED responses $(grep -c '^resp .*opcode=6' "$R/client.out"); other responses $(grep '^resp ' "$R/client.out" | grep -vc 'opcode=6')"; HP=""
  sleep "$REL"
  sample "$R" R
  { echo "NTFDISCARD=$(cnt NTFDISCARD)"; echo "NTFFAIL=$(cnt NTFFAIL)"
    for p in OutOfDirectMemoryError 'java.lang.OutOfMemoryError:' 'Request is too big'; do
      echo "systemlog[$p]=$(grep -c "$p" "$D/logs/system.log")"; echo "stdout[$p]=$(grep -c "$p" "$D/node-stdout.log")"; done
    echo "systemlog_ERROR_lines=$(grep -c '^ERROR' "$D/logs/system.log")"; } > "$R/counts.txt"
  log "counts: $(tr '\n' ' ' < "$R/counts.txt")"
  grep -E '^NTF(DISCARD|FAIL|MEM) ' "$D/node-stdout.log" > "$R/btm-lines.txt"
  grep -E '^(ERROR|WARN)' "$D/logs/system.log" > "$R/system-warn-error.txt"
  cp "$D/logs/system.log" "$R/system.log"; cp "$D/node-stdout.log" "$R/node-stdout.log"
  stop_node
  [ "$(ndaemons)" = 0 ] || { log "ABORT: daemon left after arm $name"; exit 1; }
}

for a in $ARMS; do arm_run "$a"; done
for a in $ARMS; do rm -rf "$C/node-${a%%:*}"; done
log "node dirs removed; Cassandra daemon left: $(ndaemons); client left: $(pgrep -fc "$H/hold_prelogin.py"); :9042 listeners: $(ss -ltnH 'sport = :9042' | wc -l); user scopes left: $(systemctl --user list-units --type=scope --no-legend 'ntfs-rc-*' | wc -l)"
log "run $LABEL done"
