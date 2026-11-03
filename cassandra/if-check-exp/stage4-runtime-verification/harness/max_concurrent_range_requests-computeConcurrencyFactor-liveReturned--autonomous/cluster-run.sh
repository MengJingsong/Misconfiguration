#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C9 of 2026-10-27) of max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1   (frozen: N=288000 FETCH=5000 CFETCH=500 NPLAIN=20 NGC=3 VALUES="1 4 16 48 default" CTRL_AT=48)
#   shake: N=28800 FETCH=500 CFETCH=50 NPLAIN=3 NGC=1 VALUES="1 48 default" cluster-run.sh shake
# Three nodes on 127.0.0.1-.3 from clone C (default $W/cassandra-run51), node files $W/node-rng<N> (fresh, removed at the end).
# Node 1 (JMX 7199) is the coordinator with the Byteman probe; nodes 2/3 (JMX 7299/7399) own the 48 dense ranges (C2).
# Logs: $W/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/cluster-<label>/
# (node start/stop functions adapted from harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
N=${N:-288000}; FETCH=${FETCH:-5000}; CFETCH=${CFETCH:-500}; NPLAIN=${NPLAIN:-20}; NGC=${NGC:-3}
VALUES=${VALUES:-"1 4 16 48 default"}; CTRL_AT=${CTRL_AT:-48}; CHUNKS=${CHUNKS:-6}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run51}
BIN=${W:?}/harness-bin-rng
L=${W:?}/logs/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned/cluster-$LABEL; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
run() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local rc=$?; log "  rc=$rc"; return $rc; }
NT() { local port=$1; shift; "$C/bin/nodetool" -h 127.0.0.1 -p "$port" "$@"; }
JMX() { java -cp "$BIN/jmx" RngJmx "$@"; }
CLIENT() { python3 "$H/rng-client.py" "$@"; }
ndir() { echo "${W:?}/node-rng$1"; }
port() { echo $((7099 + 100 * $1)); }
declare -a PID
PID[1]=""; PID[2]=""; PID[3]=""
stop_node() { # $1 = node index
  local i=$1 p=${PID[$1]}
  [ -z "$p" ] && return 0
  if kill -0 "$p" 2>/dev/null; then
    NT "$(port "$i")" stopdaemon >> "$L/commands.log" 2>&1
    local k; for k in $(seq 1 60); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
    if kill -0 "$p" 2>/dev/null; then kill "$p" 2>/dev/null; sleep 5; kill -9 "$p" 2>/dev/null; log "node$i pid $p killed after 60 s"; fi
  fi
  PID[$i]=""
  log "node$i stopped"
}
cleanup() { stop_node 3; stop_node 2; stop_node 1; rm -f "$L/gcmode.flag"; }
trap cleanup EXIT

log "cluster-run $LABEL N=$N fetch=$FETCH cfetch=$CFETCH nplain=$NPLAIN ngc=$NGC values=[$VALUES] ctrl_at=$CTRL_AT clone=$C $(git -C "$C" rev-parse HEAD) helper_sha=$(shasum -a 256 "$H/stage4/rng/RngProbe.java" | cut -c1-16) btm_sha=$(shasum -a 256 "$H/rng.btm" | cut -c1-16) jmx_sha=$(shasum -a 256 "$H/RngJmx.java" | cut -c1-16) client_sha=$(shasum -a 256 "$H/rng-client.py" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
echo "N=$N FETCH=$FETCH CFETCH=$CFETCH NPLAIN=$NPLAIN NGC=$NGC VALUES=$VALUES CTRL_AT=$CTRL_AT" > "$L/params.txt"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 7299 7399 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
for ip in 127.0.0.2 127.0.0.3; do ifconfig lo0 | grep -q "inet $ip " || { log "ABORT: $ip not on lo0"; exit 1; }; done
rm -rf "${BIN:?}"; mkdir -p "$BIN/classes" "$BIN/jmx"
javac -d "$BIN/classes" -cp "$C/build/classes/main:$C/build/lib/jars/*" "$H/stage4/rng/RngProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: helper compile"; exit 1; }
( cd "$BIN/classes" && jar cf "$BIN/rng-helper.jar" stage4 ) || { log "ABORT: helper jar"; exit 1; }
javac -d "$BIN/jmx" "$H/RngJmx.java" >> "$L/commands.log" 2>&1 || { log "ABORT: jmx client compile"; exit 1; }
java -cp "$C/build/lib/jars/byteman-4.0.20.jar:$BIN/rng-helper.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/rng.btm" > "$L/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$L/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
log "helper jar and JMX client built; rules type-checked: $(tail -1 "$L/btm-check.txt")"

# C2 tokens
python3 - > "$L/tokens.txt" <<'PY'
n1 = -9223372036854775000
s = ((2**63 - 1 - 808) - n1) // 48
t = [n1 + (j + 1) * s for j in range(48)]
assert t[-1] == 9223372036854774968 and s == 384307168202282291
print("node1", n1)
print("node2", ",".join(str(x) for j, x in enumerate(t) if j % 2 == 0))
print("node3", ",".join(str(x) for j, x in enumerate(t) if j % 2 == 1))
PY
[ $? = 0 ] || { log "ABORT: token generation"; exit 1; }
tok() { awk -v n="node$1" '$1==n{print $2}' "$L/tokens.txt"; }

make_node() { # $1 = index
  local i=$1 ip=127.0.0.$1 D; D=$(ndir "$1")
  rm -rf "${D:?}"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml nt=24; [ "$i" = 1 ] && nt=1
  grep -v -E '^(cluster_name|num_tokens|initial_token|allocate_tokens_for_local_replication_factor|listen_address|rpc_address|auto_bootstrap|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (B3a, amendments C1/C2 of 2026-10-27) ---
cluster_name: 'rng'
num_tokens: $nt
initial_token: $(tok "$i")
listen_address: $ip
rpc_address: $ip
auto_bootstrap: false
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
YAML
  sed -i '' "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$(port "$i")\"/" "$D/conf/cassandra-env.sh"
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-node$i.diff"
  diff "$C/conf/cassandra-env.sh" "$D/conf/cassandra-env.sh" > "$L/env-node$i.diff"
  return 0
}
set_knob() { # $1 = value or "default"
  local O; O=$(ndir 1)/conf/jvm-server.options
  grep -v '^-Dcassandra.max_concurrent_range_requests=' "$C/conf/jvm-server.options" > "$O"
  [ "$1" != default ] && echo "-Dcassandra.max_concurrent_range_requests=$1" >> "$O"
  diff "$C/conf/jvm-server.options" "$O" > "$L/$1/jvm-server-options.diff"
  return 0
}
start_node() { # $1 = index
  local i=$1 D; D=$(ndir "$1")
  local extra="" heap=2G newsz=400M
  if [ "$i" = 1 ]; then
    heap=4G; newsz=800M
    extra="-Xlog:gc*:file=$D/gc-b3.log:time,uptime -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/rng.btm,sys:$BIN/rng-helper.jar -Drng.out=$L/probe-all.txt -Drng.flag=$L/gcmode.flag"
  fi
  ( cd "$C" && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=$heap HEAP_NEWSIZE=$newsz JVM_EXTRA_OPTS="$extra" \
    exec bin/cassandra -f > "$D/node-stdout.log" 2>&1 < /dev/null ) &
  PID[$i]=$!
  log "started node$i pid=${PID[$i]} heap=$heap"
}
wait_up() { # $1 = index, $2 = number of UN nodes required in its view
  local i=$1 want=$2 k
  for k in $(seq 1 150); do
    kill -0 "${PID[$i]}" 2>/dev/null || { log "node$i died during start"; return 1; }
    if [ "$(NT "$(port "$i")" statusbinary 2>/dev/null)" = "running" ] && [ "$(NT "$(port "$i")" status 2>/dev/null | grep -c '^UN')" -ge "$want" ]; then
      log "node$i: binary running and $want UN after ~$((k*2)) s"; return 0; fi
    sleep 2
  done
  log "node$i not up after 300 s"; return 1
}
off() { local n; n=$(wc -l < "$L/probe-all.txt" 2>/dev/null | tr -d ' '); echo "${n:-0}"; }
cut_probe() { # $1 = from offset, $2 = out file
  tail -n +$(( $1 + 1 )) "$L/probe-all.txt" > "$2"; log "probe lines -> $(basename "$(dirname "$2")")/$(basename "$2"): $(wc -l < "$2" | tr -d ' ') (BATCH $(grep -c '^BATCH' "$2"), RESP $(grep -c '^RESP' "$2"), CLOSE $(grep -c '^CLOSE' "$2"), ERR $(grep -c '^ERR' "$2"))"
}
RECV="org.apache.cassandra.metrics:type=InboundConnection,scope=127.0.0.2_7000,name=ReceivedBytes::Value org.apache.cassandra.metrics:type=InboundConnection,scope=127.0.0.3_7000,name=ReceivedBytes::Value"
DROP="org.apache.cassandra.metrics:type=Connection,scope=127.0.0.1_7000,name=LargeMessageDroppedTasks::Value org.apache.cassandra.metrics:type=Connection,scope=127.0.0.1_7000,name=SmallMessageDroppedTasks::Value"
recv() { JMX 127.0.0.1:7199 $RECV > "$1" 2>&1; log "recv $(basename "$1"): $(tr '\n' ' ' < "$1")"; }
drops() { { JMX 127.0.0.1:7299 $DROP | sed 's/^/node2 /'; JMX 127.0.0.1:7399 $DROP | sed 's/^/node3 /'; } > "$1" 2>&1; log "drops $(basename "$1"): $(tr '\n' ' ' < "$1")"; }
queries() { # $1 = out jsonl, $2 = fetch, $3 = trace, $4 = count, $5 = gap
  CLIENT query "$2" "$3" "$4" "$5" > "$1" 2> "${1%.jsonl}.err"; local rc=$?
  log "queries $(basename "$1") rc=$rc ok=$(grep -c '"ok": true' "$1") rows=$(grep -o '"rows": [0-9]*' "$1" | awk '{print $2}' | sort | uniq -c | tr '\n' ' ')"
}

# 1) ring, schema, load, flush
for i in 1 2 3; do make_node $i; done
start_node 1; wait_up 1 1 || { log "ABORT: node1 did not start"; tail -30 "$(ndir 1)/node-stdout.log" >> "$L/commands.log"; exit 1; }
start_node 2; wait_up 2 2 || { log "ABORT: node2 did not start"; tail -30 "$(ndir 2)/node-stdout.log" >> "$L/commands.log"; exit 1; }
start_node 3; wait_up 3 3 || { log "ABORT: node3 did not start"; tail -30 "$(ndir 3)/node-stdout.log" >> "$L/commands.log"; exit 1; }
wait_up 1 3 || exit 1
NT 7199 ring > "$L/ring.txt" 2>&1; log "ring: $(grep -c '127.0.0.1 ' "$L/ring.txt") node1 tokens, $(grep -c '127.0.0.2 ' "$L/ring.txt") node2, $(grep -c '127.0.0.3 ' "$L/ring.txt") node3"
CLIENT schema > "$L/schema.json" 2>&1 || { log "ABORT: schema $(cat "$L/schema.json")"; exit 1; }
log "schema: $(cat "$L/schema.json")"
step=$(( (N + CHUNKS - 1) / CHUNKS )); lo=0
while [ $lo -lt "$N" ]; do hi=$((lo + step)); [ $hi -gt "$N" ] && hi=$N
  CLIENT load "$N" $lo $hi > "$L/load-$hi.json" 2>&1; log "load $lo..$hi rc=$? $(cat "$L/load-$hi.json")"; lo=$hi; done
for i in 1 2 3; do run NT "$(port $i)" flush rng; done
for i in 1 2 3; do NT "$(port $i)" tablestats rng.t > "$L/tablestats-node$i.txt" 2>&1; log "node$i tablestats: $(grep -E 'SSTable count|Number of partitions' "$L/tablestats-node$i.txt" | tr -s ' ' | tr '\n' ';')"; done
du -sk "$(ndir 1)/data" "$(ndir 2)/data" "$(ndir 3)/data" > "$L/data-du.txt"

# 2) per value
touch "$L/probe-all.txt"
for V in $VALUES; do
  R=$L/$V; mkdir -p "$R"
  log "=== value $V ==="
  stop_node 1
  set_knob "$V"
  start_node 1; wait_up 1 3 || { log "ABORT: node1 did not restart for $V"; tail -30 "$(ndir 1)/node-stdout.log" >> "$L/commands.log"; exit 1; }
  ps -o command= -p "$(pgrep -f "cassandra.logdir=$(ndir 1)/logs" | head -1)" | tr ' ' '\n' | grep -E 'max_concurrent_range_requests|Xmx|byteman' > "$R/node1-cmdline.txt"
  log "node1 cmdline: $(tr '\n' ' ' < "$R/node1-cmdline.txt")"
  sleep 10
  o=$(off); queries "$R/trace.jsonl" "$FETCH" 1 1 0; sleep 2; cut_probe "$o" "$R/probe-trace.txt"
  drops "$R/drops-before.txt"
  recv "$R/recv-before.txt"
  o=$(off); queries "$R/plain.jsonl" "$FETCH" 0 "$NPLAIN" 2; sleep 2
  recv "$R/recv-after.txt"; cut_probe "$o" "$R/probe-plain.txt"
  touch "$L/gcmode.flag"
  o=$(off); queries "$R/gc.jsonl" "$FETCH" 0 "$NGC" 5; sleep 2; cut_probe "$o" "$R/probe-gc.txt"
  rm -f "$L/gcmode.flag"
  if [ "$V" = "$CTRL_AT" ]; then
    recv "$R/ctl-recv-before.txt"
    o=$(off); queries "$R/ctl.jsonl" "$CFETCH" 0 "$NPLAIN" 2; sleep 2
    recv "$R/ctl-recv-after.txt"; cut_probe "$o" "$R/probe-ctl.txt"
  fi
  drops "$R/drops-after.txt"
  grep -E '^(ERROR|WARN)' "$(ndir 1)/logs/system.log" | grep -v -E 'Small commitlog volume|swap|Unable to lock JVM memory|jemalloc|OpenJDK|JMX is not enabled|Non-UTC|Using AWS|dynamic_snitch' | tail -40 > "$R/node1-errwarn.txt"
done

# 3) collect, stop, clean
for i in 1 2 3; do cp "$(ndir $i)/logs/system.log" "$L/node$i-system.log"; done
cp "$(ndir 1)/gc-b3.log"* "$L/" 2>/dev/null
grep -E '^(ERROR|WARN)' "$(ndir 2)/logs/system.log" "$(ndir 3)/logs/system.log" | grep -v -E 'Small commitlog volume|swap|Unable to lock JVM memory|jemalloc|OpenJDK|JMX is not enabled|Non-UTC|Using AWS|dynamic_snitch' | tail -60 > "$L/node23-errwarn.txt"
stop_node 3; stop_node 2; stop_node 1
sleep 3
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && log "WARNING: daemon still present" || log "no Cassandra daemon left"
du -sk "$(ndir 1)" "$(ndir 2)" "$(ndir 3)" > "$L/node-du.txt"
for i in 1 2 3; do rm -rf "$(ndir $i)"; done
log "cluster-run $LABEL done; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
