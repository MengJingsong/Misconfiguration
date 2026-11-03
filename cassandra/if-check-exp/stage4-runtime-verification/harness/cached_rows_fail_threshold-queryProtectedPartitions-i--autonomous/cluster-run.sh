#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C7 of 2026-10-27) of cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   r1:    cluster-run.sh r1     (frozen values: N=100000, CHUNK=20000, TS="1000 10000 32000 1000000", REPS=2, ONE_T=1000000)
#   shake: N=4000 CHUNK=2000 TS="100 1000 32000 100000" REPS=2 cluster-run.sh shake
# Two nodes (127.0.0.1 JMX 7199 with the Byteman probe; 127.0.0.2 JMX 7299) from clone C (default $W/cassandra-run50),
# node files $W/node-rfp1, $W/node-rfp2 (fresh, removed at the end). Logs: $W/logs/cached_rows_fail_threshold-queryProtectedPartitions-i/cluster-<label>/
# (node start/stop functions adapted from harness/paxos_cache_size-close-active--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1
N=${N:-100000}; CHUNK=${CHUNK:-20000}; TS=${TS:-"1000 10000 32000 1000000"}; REPS=${REPS:-2}; ONE_T=${ONE_T:-1000000}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run50}
BIN=$W/harness-bin-rfp
L=$W/logs/cached_rows_fail_threshold-queryProtectedPartitions-i/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
run() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local rc=$?; log "  rc=$rc"; return $rc; }
NT() { local port=$1; shift; "$C/bin/nodetool" -h 127.0.0.1 -p "$port" "$@"; }
JMX() { java -cp "$BIN/jmx" RfpJmx "$@"; }
CLIENT() { python3 "$H/rfp-client.py" "$@"; }
ndir() { echo "$W/node-rfp$1"; }
port() { [ "$1" = 1 ] && echo 7199 || echo 7299; }
declare -a PID
PID[1]=""; PID[2]=""
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
cleanup() { stop_node 2; stop_node 1; [ -n "${SP:-}" ] && kill "$SP" 2>/dev/null; }
trap cleanup EXIT

log "cluster-run $LABEL N=$N chunk=$CHUNK TS=[$TS] reps=$REPS one_T=$ONE_T clone=$C $(git -C "$C" rev-parse HEAD) helper_sha=$(shasum -a 256 "$H/stage4/rfp/RfpProbe.java" | cut -c1-16) btm_sha=$(shasum -a 256 "$H/rfp.btm" | cut -c1-16) jmx_sha=$(shasum -a 256 "$H/RfpJmx.java" | cut -c1-16) client_sha=$(shasum -a 256 "$H/rfp-client.py" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 7299 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
ifconfig lo0 | grep -q 'inet 127.0.0.2 ' || { log "ABORT: 127.0.0.2 not on lo0"; exit 1; }
rm -rf "$BIN"; mkdir -p "$BIN/classes" "$BIN/jmx"
javac -d "$BIN/classes" -cp "$C/build/classes/main:$C/build/lib/jars/*" "$H/stage4/rfp/RfpProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: helper compile"; exit 1; }
( cd "$BIN/classes" && jar cf "$BIN/rfp-helper.jar" stage4 ) || { log "ABORT: helper jar"; exit 1; }
javac -d "$BIN/jmx" "$H/RfpJmx.java" >> "$L/commands.log" 2>&1 || { log "ABORT: jmx client compile"; exit 1; }
java -cp "$C/build/lib/jars/byteman-4.0.20.jar:$BIN/rfp-helper.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/rfp.btm" > "$L/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$L/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
log "helper jar and JMX client built; rules type-checked: $(tail -1 "$L/btm-check.txt")"

make_node() { # $1 = index, $2 = ip
  local i=$1 ip=$2 D; D=$(ndir "$1")
  rm -rf "$D"; mkdir -p "$D"/data "$D"/commitlog "$D"/hints "$D"/saved_caches "$D"/cdc_raw "$D"/logs
  cp -R "$C/conf" "$D/conf"
  local Y=$D/conf/cassandra.yaml
  grep -v -E '^(cluster_name|num_tokens|listen_address|rpc_address|hinted_handoff_enabled|auto_bootstrap|read_request_timeout|range_request_timeout|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (B3a, amendment C1 of 2026-10-27) ---
cluster_name: 'rfp'
num_tokens: 16
listen_address: $ip
rpc_address: $ip
hinted_handoff_enabled: false
auto_bootstrap: false
read_request_timeout: 60000ms
range_request_timeout: 60000ms
data_file_directories:
    - $D/data
commitlog_directory: $D/commitlog
hints_directory: $D/hints
saved_caches_directory: $D/saved_caches
cdc_raw_directory: $D/cdc_raw
YAML
  if [ "$i" = 2 ]; then sed -i '' 's/^JMX_PORT="7199"/JMX_PORT="7299"/' "$D/conf/cassandra-env.sh"; fi
  diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-node$i.diff"
  diff "$C/conf/cassandra-env.sh" "$D/conf/cassandra-env.sh" > "$L/env-node$i.diff"
  return 0
}
start_node() { # $1 = index
  local i=$1 D; D=$(ndir "$1")
  local extra=""
  [ "$i" = 1 ] && extra="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/rfp.btm,sys:$BIN/rfp-helper.jar -Drfp.out=$L/probe-all.txt"
  ( cd "$C" && CASSANDRA_CONF=$D/conf CASSANDRA_LOG_DIR=$D/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M JVM_EXTRA_OPTS="$extra" \
    exec bin/cassandra -f > "$D/node-stdout.log" 2>&1 < /dev/null ) &
  PID[$i]=$!
  log "started node$i pid=${PID[$i]}"
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
wait_view() { # node 1's view: $1 = UN count wanted, $2 = DN count wanted
  local k
  for k in $(seq 1 90); do
    local s; s=$(NT 7199 status 2>/dev/null)
    if [ "$(echo "$s" | grep -c '^UN')" = "$1" ] && [ "$(echo "$s" | grep -c '^DN')" = "$2" ]; then log "node1 view: UN=$1 DN=$2 after ~$((k*2)) s"; return 0; fi
    sleep 2
  done
  log "node1 view not UN=$1 DN=$2 after 180 s"; NT 7199 status >> "$L/commands.log" 2>&1; return 1
}
sampler() { # $1 = output file; class histogram every 2 s (informational, B3d (3))
  while true; do
    echo "SAMPLE $(perl -MTime::HiRes=time -e 'printf "%d", time*1000')" >> "$1"
    jcmd "$JP" GC.class_histogram 2>/dev/null | awk '$4=="org.apache.cassandra.db.rows.BTreeRow"||$4=="org.apache.cassandra.db.rows.BufferCell"||$4=="java.nio.HeapByteBuffer"||$4=="[B"||$1=="Total"' >> "$1"
    sleep 2
  done
}
one_query() { # $1 = tag, $2 = T, $3 = CL
  local tag=$1 T=$2 CL=$3 R=$L/$1; mkdir -p "$R"
  log "--- $tag: T=$T CL=$CL ---"
  JMX 127.0.0.1:7199 set "$T" > "$R/threshold.txt" 2>&1; log "threshold: $(cat "$R/threshold.txt")"
  JMX 127.0.0.1:7199 hist rfp t > "$R/hist-before.txt" 2>&1; log "hist before: $(cat "$R/hist-before.txt")"
  local off; off=$(wc -l < "$L/probe-all.txt" 2>/dev/null | tr -d ' '); off=${off:-0}
  sampler "$R/histo-samples.txt" & SP=$!
  CLIENT query "$CL" > "$R/query.json" 2> "$R/query.err"; local rc=$?
  kill "$SP" 2>/dev/null; wait "$SP" 2>/dev/null; SP=""
  log "query rc=$rc $(cat "$R/query.json")"
  sleep 1
  JMX 127.0.0.1:7199 hist rfp t > "$R/hist-after.txt" 2>&1; log "hist after: $(cat "$R/hist-after.txt")"
  tail -n +$((off + 1)) "$L/probe-all.txt" > "$R/probe.txt" 2>/dev/null
  log "probe lines: $(wc -l < "$R/probe.txt" | tr -d ' ')"; while read -r pl; do log "  $pl"; done < "$R/probe.txt"
  jcmd "$JP" GC.run >> "$L/commands.log" 2>&1
  sleep 10
}

make_node 1 127.0.0.1; make_node 2 127.0.0.2
start_node 1; wait_up 1 1 || { log "ABORT: node1 did not start"; tail -30 "$(ndir 1)/node-stdout.log" >> "$L/commands.log"; exit 1; }
start_node 2; wait_up 2 2 || { log "ABORT: node2 did not start"; tail -30 "$(ndir 2)/node-stdout.log" >> "$L/commands.log"; exit 1; }
wait_view 2 0 || exit 1
JP=$(pgrep -f "cassandra.logdir=$(ndir 1)/logs" | head -1); log "node1 java pid=$JP"
grep -i 'byteman' "$(ndir 1)/node-stdout.log" | head -3 >> "$L/commands.log"
CLIENT settings > "$L/settings.json" 2>&1; log "settings: $(cat "$L/settings.json")"
CLIENT schema > "$L/schema.json" 2>&1 || { log "ABORT: schema $(cat "$L/schema.json")"; exit 1; }
log "schema: $(cat "$L/schema.json")"
lo=0; while [ $lo -lt "$N" ]; do hi=$((lo + CHUNK)); [ $hi -gt "$N" ] && hi=$N
  CLIENT load $lo $hi > "$L/load-$hi.json" 2>&1; log "load $lo..$hi rc=$? $(cat "$L/load-$hi.json")"; lo=$hi; done
run NT 7299 drain
stop_node 2
wait_view 1 1 || exit 1
lo=0; while [ $lo -lt "$N" ]; do hi=$((lo + CHUNK)); [ $hi -gt "$N" ] && hi=$N
  CLIENT diverge $lo $hi > "$L/diverge-$hi.json" 2>&1; log "diverge $lo..$hi rc=$? $(cat "$L/diverge-$hi.json")"; lo=$hi; done
start_node 2; wait_up 2 2 || { log "ABORT: node2 did not restart"; exit 1; }
wait_view 2 0 || exit 1
sleep 10
jcmd "$JP" GC.run >> "$L/commands.log" 2>&1
jcmd "$JP" GC.class_histogram > "$L/histo-baseline.txt" 2>&1
log "baseline histogram: $(awk '$4=="org.apache.cassandra.db.rows.BTreeRow"{print "BTreeRow="$2}' "$L/histo-baseline.txt") $(awk '$1=="Total"{print "total_bytes="$3}' "$L/histo-baseline.txt")"
touch "$L/probe-all.txt"; log "probe lines before the queries: $(wc -l < "$L/probe-all.txt" | tr -d ' ')"
for T in $TS; do
  for r in $(seq 1 "$REPS"); do one_query "T$T-r$r" "$T" ALL; done
done
one_query "ONE-T$ONE_T" "$ONE_T" ONE
grep -E '^(ERROR|WARN)' "$(ndir 1)/logs/system.log" | grep -v -E 'Small commitlog volume|swap|Unable to lock JVM memory|jemalloc|OpenJDK|JMX is not enabled|Non-UTC|Using AWS|dynamic_snitch' | head -80 > "$L/node1-errwarn.txt"
grep -c -E 'ReplicaFilteringProtection\.java:[0-9]+ - Replica filtering protection has cached over' "$(ndir 1)/logs/system.log" > "$L/node1-rfp-error-count.txt"
grep 'Replica filtering protection has cached over' "$(ndir 1)/logs/system.log" | cut -c1-300 > "$L/node1-rfp-error-lines.txt"
cp "$(ndir 1)/logs/system.log" "$L/node1-system.log"; cp "$(ndir 2)/logs/system.log" "$L/node2-system.log"
cp "$(ndir 1)"/logs/gc.log* "$L/" 2>/dev/null
NT 7199 tablestats rfp.t > "$L/tablestats-node1.txt" 2>&1
stop_node 2; stop_node 1
sleep 3
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && log "WARNING: daemon still present" || log "no Cassandra daemon left"
du -sk "$(ndir 1)" "$(ndir 2)" > "$L/node-du.txt"; rm -rf "$(ndir 1)" "$(ndir 2)"
log "cluster-run $LABEL done; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
