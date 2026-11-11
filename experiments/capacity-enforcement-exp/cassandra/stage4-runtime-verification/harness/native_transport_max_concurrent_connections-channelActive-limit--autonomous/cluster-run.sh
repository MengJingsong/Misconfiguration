#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C9 of 2026-10-27) of native_transport_max_concurrent_connections-channelActive-limit--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1     (frozen values: N=300 NC=100 S=4194295 LA=200 LB=50 WARM=60 SETTLE=20)
#   shake: N=30 NC=10 S=1048566 LA=20 LB=5 WARM=5 SETTLE=3 cluster-run.sh shake
# One node (127.0.0.1, JMX 7199, Byteman rules ntc.btm) from clone C (default $W/cassandra-run53), node files $W/node-ntc
# (fresh per node start, removed at the end). Logs: $W/logs/native_transport_max_concurrent_connections-channelActive-limit/cluster-<label>/
# (node start/stop and logging adapted from harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
N=${N:-300}; NC=${NC:-100}; S=${S:-4194295}; LA=${LA:-200}; LB=${LB:-50}; WARM=${WARM:-60}; SETTLE=${SETTLE:-20}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run53}
D=$W/node-ntc
L=$W/logs/native_transport_max_concurrent_connections-channelActive-limit/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
PID=""; JP=""; HP=""
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
kill_holds() { pkill -f "$H/hold.py" 2>/dev/null; sleep 1; pkill -9 -f "$H/hold.py" 2>/dev/null; return 0; }
MAINPID=$$
cleanup() { local me; me=$(exec sh -c 'echo $PPID'); [ "$me" = "$MAINPID" ] || return 0; kill_holds; stop_node; }  # bash 3.2: act only in the main shell
trap cleanup EXIT

log "cluster-run $LABEL N=$N NC=$NC S=$S LA=$LA LB=$LB WARM=$WARM SETTLE=$SETTLE clone=$C $(git -C "$C" rev-parse HEAD) hold_sha=$(shasum -a 256 "$H/hold.py" | cut -c1-16) btm_sha=$(shasum -a 256 "$H/ntc.btm" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
java -cp "$C/build/lib/jars/byteman-4.0.20.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/ntc.btm" > "$L/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$L/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
log "rule type-checked: $(tail -1 "$L/btm-check.txt"); $(python3 --version 2>&1); ulimit -n $(ulimit -n)"

make_node() { # $1 = limit
  rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|native_transport_max_concurrent_connections):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (B3a/B3b, amendment C1 of 2026-10-27) ---
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
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-$TAGN.diff"
  return 0
}
start_node() {
  local extra="-Dcassandra.netty_use_heap_allocator=true -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/ntc.btm"
  ( cd "$C" && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M JVM_EXTRA_OPTS="$extra" \
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
gcrun() { jcmd "$JP" GC.run > /dev/null 2>&1; sleep 2; }
histo() { # $1 = out file -> "Total [B"
  jcmd "$JP" GC.class_histogram > "$1" 2>&1
  echo "$(awk '$1=="Total"{print $3}' "$1") $(awk '$4=="[B"{print $3}' "$1")"
}
est9042() { # $1 = out file -> node-side ESTABLISHED connections on 127.0.0.1.9042
  netstat -an -p tcp > "$1" 2>&1
  awk '$6=="ESTABLISHED" && $4=="127.0.0.1.9042"' "$1" | wc -l | tr -d ' '
}
amem() { # $1 = out file: one NTCMEM line triggered by nodetool version (amendment C4)
  local before after k; before=$(grep -c '^NTCMEM ' "$D/node-stdout.log" 2>/dev/null); before=${before:-0}
  NT version > /dev/null 2>&1
  for k in $(seq 1 20); do after=$(grep -c '^NTCMEM ' "$D/node-stdout.log" 2>/dev/null); [ "${after:-0}" -gt "$before" ] && break; sleep 0.5; done
  grep '^NTCMEM ' "$D/node-stdout.log" | tail -1 > "$1"
  cat "$1"
}
nrefuse() { local n; n=$(grep -c '^NTCREFUSE ' "$D/node-stdout.log" 2>/dev/null); echo "${n:-0}"; }
nlog() { local n; n=$(grep -c 'Exceeded maximum native connection limit' "$D/logs/system.log" 2>/dev/null); echo "${n:-0}"; }

one_run() { # $1 = tag, $2 = N, $3 = S
  local tag=$1 n=$2 s=$3 R=$L/$1; mkdir -p "$R"
  log "--- run $tag: N=$n S=$s ---"
  local r0 l0; r0=$(nrefuse); l0=$(nlog)
  gcrun
  log "baseline histo (Total, [B): $(histo "$R/histo-base.txt")"
  log "baseline alloc: $(amem "$R/alloc-base.txt")"
  log "baseline :9042 established: $(est9042 "$R/netstat-0.txt")"
  python3 "$H/hold.py" 127.0.0.1 9042 "$n" "$s" > "$R/hold.out" 2> "$R/hold.err" &
  HP=$!
  local k ok=0
  for k in $(seq 1 120); do grep -q '^held=' "$R/hold.out" 2>/dev/null && { ok=1; break; }; sleep 1; done
  log "held line after ~$k s: $(grep '^held=' "$R/hold.out")"
  [ "$ok" = 1 ] || log "STOP CONDITION: hold.py printed no held= line within 120 s (run invalid)"
  log ":9042 established after held: $(est9042 "$R/netstat-1.txt")"
  sleep "$SETTLE"
  gcrun
  log "reading histo (Total, [B): $(histo "$R/histo-read.txt")"
  log "reading alloc: $(amem "$R/alloc-read.txt")"
  log ":9042 established at reading: $(est9042 "$R/netstat-2.txt")"
  log "log lines in run: $(( $(nlog) - l0 )) (node cumulative $(nlog)); NTCREFUSE lines in run: $(( $(nrefuse) - r0 ))"
  grep 'Exceeded maximum native connection limit' "$D/logs/system.log" > "$R/limit-log-lines.txt"
  grep '^NTCREFUSE ' "$D/node-stdout.log" | tail -n +"$((r0 + 1))" > "$R/ntcrefuse.txt"
  kill -TERM "$HP" 2>/dev/null; wait "$HP" 2>/dev/null; HP=""
  log "hold.py left: $(pgrep -f "$H/hold.py" | wc -l | tr -d ' ')"
  sleep 5
  log ":9042 established after kill: $(est9042 "$R/netstat-3.txt")"
  sleep 2
  gcrun
  log "post histo (Total, [B): $(histo "$R/histo-post.txt")"
  log "post alloc: $(amem "$R/alloc-post.txt")"
}

node_run() { # $1 = node tag, $2 = limit, then run specs "tag|N|S" ...
  TAGN=$1; local lim=$2; shift 2
  log "=== node $TAGN: native_transport_max_concurrent_connections=$lim ==="
  make_node "$lim"
  start_node; wait_up || { log "ABORT: node did not start"; tail -30 "$D/node-stdout.log" >> "$L/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); log "node java pid=$JP"
  grep -o 'native_transport_max_concurrent_connections=[^;]*; native_transport_max_concurrent_connections_per_ip=[^;]*' "$D/logs/system.log" | head -1 > "$L/$TAGN-config.txt"
  log "config: $(cat "$L/$TAGN-config.txt")"
  grep -o 'native_transport_idle_timeout=[^;]*' "$D/logs/system.log" | head -1 >> "$L/$TAGN-config.txt"
  local i
  for i in 1 2 3; do "$C/bin/cqlsh" 127.0.0.1 9042 -e "SELECT now() FROM system.local" >> "$L/$TAGN-cqlsh-warm.txt" 2>&1; log "warm-up cqlsh $i rc=$?"; done
  sleep "$WARM"
  local spec t n s
  for spec in "$@"; do
    IFS='|' read -r t n s <<< "$spec"
    one_run "$TAGN-$t" "$n" "$s"
  done
  cp "$D/node-stdout.log" "$L/$TAGN-node-stdout.log"; cp "$D/logs/system.log" "$L/$TAGN-system.log"
  stop_node
}

node_run lm1 -1 "main|$N|$S" "n100|$NC|$S" "s0|$N|-1"
node_run l$LA "$LA" "main|$N|$S"
node_run l$LB "$LB" "main|$N|$S"
rm -rf "$D"
log "node files removed; Cassandra daemon left: $(ps -eo command | grep -c 'org.apache.cassandra.service.Cassandra[D]aemon'); hold.py left: $(pgrep -f "$H/hold.py" | wc -l | tr -d ' '); :9042 listeners: $(lsof -nP -iTCP:9042 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' '); clone status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
log "cluster-run $LABEL done"
