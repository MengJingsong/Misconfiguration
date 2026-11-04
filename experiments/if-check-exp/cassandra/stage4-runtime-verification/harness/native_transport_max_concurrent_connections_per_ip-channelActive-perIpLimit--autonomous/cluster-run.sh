#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C9 and runbook fix D2 of 2026-10-27) of native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1                     (frozen values: M=60 S=4194295 WARM=60 SETTLE=20)
#   shake: M=6 S=1048566 WARM=5 SETTLE=3 cluster-run.sh shake
# One node (127.0.0.1, JMX 7199, Byteman rule ntpip.btm) from clone C (default $W/cassandra-run52), node files $W/node-ntpip
# (fresh per node start, removed at the end). Logs: $W/logs/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit/cluster-<label>/
# (node start/stop functions adapted from harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
M=${M:-60}; S=${S:-4194295}; WARM=${WARM:-60}; SETTLE=${SETTLE:-20}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run52}
D=$W/node-ntpip
L=$W/logs/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
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
  log "node stopped; CassandraDaemon processes left: $(ps -eo command | grep -c '[C]assandraDaemon')"
}
kill_holds() { pkill -f "$H/hold.py" 2>/dev/null; sleep 1; pkill -9 -f "$H/hold.py" 2>/dev/null; return 0; }
MAINPID=$$
cleanup() { local me; me=$(exec sh -c 'echo $PPID'); [ "$me" = "$MAINPID" ] || return 0; kill_holds; stop_node; }  # bash 3.2: no BASHPID; act only in the main shell
trap cleanup EXIT

log "cluster-run $LABEL M=$M S=$S WARM=$WARM SETTLE=$SETTLE clone=$C $(git -C "$C" rev-parse HEAD) hold_sha=$(shasum -a 256 "$H/hold.py" | cut -c1-16) btm_sha=$(shasum -a 256 "$H/ntpip.btm" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
for a in 127.0.0.2 127.0.0.3; do ifconfig lo0 | grep -q "inet $a " || { log "ABORT: $a not on lo0"; exit 1; }; done
java -cp "$C/build/lib/jars/byteman-4.0.20.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/ntpip.btm" > "$L/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$L/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
log "rule type-checked: $(tail -1 "$L/btm-check.txt"); python3 $(python3 --version 2>&1); ulimit -n $(ulimit -n)"

make_node() { # $1 = global limit, $2 = per-IP limit
  rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|native_transport_max_concurrent_connections|native_transport_max_concurrent_connections_per_ip):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (B3a/B3b, amendments C1-C2 of 2026-10-27) ---
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
native_transport_max_concurrent_connections: $1
native_transport_max_concurrent_connections_per_ip: $2
YAML
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-$TAGN.diff"
  return 0
}
start_node() {
  local extra="-Dcassandra.netty_use_heap_allocator=true -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/ntpip.btm"
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
histo() { # $1 = out file
  jcmd "$JP" GC.class_histogram > "$1" 2>&1
  echo "$(awk '$1=="Total"{print $3}' "$1") $(awk '$4=="[B"{print $3}' "$1")"
}
est9042() { # $1 = out file -> per-IP counts of node-side established :9042 connections
  netstat -an -p tcp > "$1" 2>&1
  awk '$6=="ESTABLISHED" && $4 ~ /\.9042$/ {n=split($5,a,"."); print a[1]"."a[2]"."a[3]"."a[4]}' "$1" | sort | uniq -c | awk '{printf "%s=%s ", $2, $1}'
  echo "total=$(awk '$6=="ESTABLISHED" && $4 ~ /\.9042$/' "$1" | wc -l | tr -d ' ')"
}
amem() { # $1 = out file: one NTPIPMEM line triggered by nodetool version (runbook fix D2)
  local before after k; before=$(grep -c '^NTPIPMEM ' "$D/node-stdout.log" 2>/dev/null); before=${before:-0}
  NT version > /dev/null 2>&1
  for k in $(seq 1 20); do after=$(grep -c '^NTPIPMEM ' "$D/node-stdout.log" 2>/dev/null); [ "${after:-0}" -gt "$before" ] && break; sleep 0.5; done
  grep '^NTPIPMEM ' "$D/node-stdout.log" | tail -1 > "$1"
  cat "$1"
}
ntpip_off() { local n; n=$(grep -c '^NTPIP ' "$D/node-stdout.log" 2>/dev/null); echo "${n:-0}"; }

one_run() { # $1 = tag, $2 = list of source IPs, $3 = S
  local tag=$1 ips=$2 s=$3 R=$L/$1; mkdir -p "$R"
  log "--- run $tag: ips=[$ips] M=$M S=$s ---"
  local off; off=$(ntpip_off)
  log "baseline histo (Total, [B): $(histo "$R/histo-base.txt")"
  log "baseline alloc: $(amem "$R/alloc-base.txt")"
  log "baseline :9042: $(est9042 "$R/netstat-0.txt")"
  local ip pids=""
  for ip in $ips; do
    python3 "$H/hold.py" 127.0.0.1 9042 "$M" "$s" "$ip" > "$R/hold-$ip.out" 2> "$R/hold-$ip.err" &
    pids="$pids $!"
  done
  local k ok=0 n; n=$(echo $ips | wc -w | tr -d ' ')
  for k in $(seq 1 120); do
    ok=$(cat "$R"/hold-*.out 2>/dev/null | grep -c '^held=')
    [ "$ok" -ge "$n" ] && break
    sleep 1
  done
  log "held lines $ok/$n after ~$k s"; for ip in $ips; do log "  $ip: $(grep '^held=' "$R/hold-$ip.out")"; done
  [ "$ok" -ge "$n" ] || log "STOP CONDITION: not every script printed held= within 120 s"
  log ":9042 after held: $(est9042 "$R/netstat-1.txt")"
  sleep "$SETTLE"
  log "reading histo (Total, [B): $(histo "$R/histo-read.txt")"
  log "reading alloc: $(amem "$R/alloc-read.txt")"
  log ":9042 at reading: $(est9042 "$R/netstat-2.txt")"
  log "per-ip log lines (node, cumulative): $(grep -c 'Exceeded maximum native connection limit per ip' "$D/logs/system.log")"
  grep 'Exceeded maximum native connection limit' "$D/logs/system.log" > "$R/limit-log-lines.txt"
  kill $pids 2>/dev/null; wait $pids 2>/dev/null
  log "hold.py left: $(pgrep -f "$H/hold.py" | wc -l | tr -d ' ')"
  sleep 5
  log ":9042 after kill: $(est9042 "$R/netstat-3.txt")"
  sleep 2
  log "post histo (Total, [B): $(histo "$R/histo-post.txt")"
  log "post alloc: $(amem "$R/alloc-post.txt")"
  local from=$((off + 1))
  grep '^NTPIP ' "$D/node-stdout.log" | tail -n +"$from" > "$R/ntpip.txt"
  log "NTPIP lines in run: $(wc -l < "$R/ntpip.txt" | tr -d ' '); last: $(tail -1 "$R/ntpip.txt")"
}

node_run() { # $1 = node tag, $2 = global, $3 = per-IP, then run specs "tag|ips|S" ...
  TAGN=$1; local g=$2 p=$3; shift 3
  log "=== node $TAGN: global=$g per-ip=$p ==="
  make_node "$g" "$p"
  start_node; wait_up || { log "ABORT: node did not start"; tail -30 "$D/node-stdout.log" >> "$L/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); log "node java pid=$JP"
  grep -o 'native_transport_max_concurrent_connections=[^;]*; native_transport_max_concurrent_connections_per_ip=[^;]*' "$D/logs/system.log" | head -1 > "$L/$TAGN-config.txt"
  log "config: $(cat "$L/$TAGN-config.txt")"
  local i
  for i in 1 2 3; do "$C/bin/cqlsh" 127.0.0.1 9042 -e "SELECT now() FROM system.local" >> "$L/$TAGN-cqlsh-warm.txt" 2>&1; log "warm-up cqlsh $i rc=$?"; done
  sleep "$WARM"
  local spec
  for spec in "$@"; do
    IFS='|' read -r t ips s <<< "$spec"
    one_run "$TAGN-$t" "$ips" "$s"
  done
  cp "$D/node-stdout.log" "$L/$TAGN-node-stdout.log"; cp "$D/logs/system.log" "$L/$TAGN-system.log"
  stop_node
}

edge_run() {
  TAGN=edge
  log "=== node edge: global=0 per-ip=10 ==="
  make_node 0 10
  start_node; wait_up || { log "ABORT: node did not start"; tail -30 "$D/node-stdout.log" >> "$L/commands.log"; exit 1; }
  JP=$(pgrep -f "cassandra.logdir=$D/logs" | head -1); log "node java pid=$JP"
  grep -o 'native_transport_max_concurrent_connections=[^;]*; native_transport_max_concurrent_connections_per_ip=[^;]*' "$D/logs/system.log" | head -1 > "$L/edge-config.txt"
  log "config: $(cat "$L/edge-config.txt")"
  local R=$L/edge; mkdir -p "$R"
  "$C/bin/cqlsh" --connect-timeout=10 127.0.0.1 9042 -e "SELECT now() FROM system.local" > "$R/cqlsh.txt" 2>&1; log "edge cqlsh rc=$? $(tr '\n' ' ' < "$R/cqlsh.txt" | cut -c1-300)"
  python3 "$H/hold.py" 127.0.0.1 9042 5 0 127.0.0.1 > "$R/hold-127.0.0.1.out" 2> "$R/hold-127.0.0.1.err" & local hp=$!
  local k; for k in $(seq 1 30); do grep -q '^held=' "$R/hold-127.0.0.1.out" && break; sleep 1; done
  log "edge hold: $(grep '^held=' "$R/hold-127.0.0.1.out")"
  log "edge :9042: $(est9042 "$R/netstat-1.txt")"
  kill $hp 2>/dev/null; wait $hp 2>/dev/null
  grep 'Exceeded maximum native connection limit' "$D/logs/system.log" > "$R/limit-log-lines.txt"
  log "edge global-limit log lines: $(grep -c 'Exceeded maximum native connection limit of' "$D/logs/system.log"); per-ip: $(grep -c 'limit per ip' "$D/logs/system.log")"
  cp "$D/node-stdout.log" "$L/edge-node-stdout.log"; cp "$D/logs/system.log" "$L/edge-system.log"
  grep '^NTPIP ' "$D/node-stdout.log" > "$R/ntpip.txt"
  log "edge alloc: $(amem "$R/alloc-edge.txt")"
  stop_node
}

node_run pm1 -1 -1 "main|127.0.0.1 127.0.0.2 127.0.0.3|$S" "s0|127.0.0.1 127.0.0.2 127.0.0.3|-1"
node_run p40 -1 40 "main|127.0.0.1 127.0.0.2 127.0.0.3|$S"
node_run p10 -1 10 "main|127.0.0.1 127.0.0.2 127.0.0.3|$S" "scope1|127.0.0.1|$S"
edge_run
rm -rf "$D"
log "node files removed; CassandraDaemon left: $(ps -eo command | grep -c '[C]assandraDaemon'); hold.py left: $(pgrep -f "$H/hold.py" | wc -l | tr -d ' '); :9042 listeners: $(lsof -nP -iTCP:9042 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' '); clone status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
log "cluster-run $LABEL done"
