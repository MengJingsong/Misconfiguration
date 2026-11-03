#!/usr/bin/env bash
# Cluster tier (B3, amendments C1-C8 of 2026-10-27) of paxos_cache_size-close-active--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label> <chunk> "<caps>"
#   r1:    cluster-run.sh r1 10000 "0 8 32 default 128 1024"   (as frozen: 5 chunks of 10,000 LWTs)
#   shake: e.g. cluster-run.sh shake 1000 "0 2 default"
# One node from clone C (default $W/cassandra-run49), node files $W/node-pcca (fresh per round, removed after it).
# Logs and raw files: $W/logs/paxos_cache_size-close-active/cluster-<label>/C<cap>/
# (node start/stop functions adapted from harness/max_hints_size_per_host-shouldHint-maxHintsSize--autonomous/cluster-run.sh)
set -uo pipefail
LABEL=$1; CHUNK=$2; CAPS=$3; NCHUNK=${NCHUNK:-5}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run49}
N=$W/node-pcca; BIN=$W/harness-bin-pcca
L=$W/logs/paxos_cache_size-close-active/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
run() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local rc=$?; log "  rc=$rc"; return $rc; }
NT() { "$C/bin/nodetool" -h 127.0.0.1 -p 7199 "$@"; }
P1=""
stop_node() {
  [ -z "$P1" ] && return 0
  if kill -0 "$P1" 2>/dev/null; then
    NT stopdaemon >> "$L/commands.log" 2>&1
    local i; for i in $(seq 1 60); do kill -0 "$P1" 2>/dev/null || break; sleep 1; done
    if kill -0 "$P1" 2>/dev/null; then kill "$P1" 2>/dev/null; sleep 5; kill -9 "$P1" 2>/dev/null; log "node pid $P1 killed after 60 s"; fi
  fi
  P1=""
  local j; for j in $(seq 1 30); do pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null || break; sleep 1; done
}
trap 'stop_node' EXIT

log "cluster-run $LABEL chunk=$CHUNK nchunk=$NCHUNK caps=[$CAPS] clone=$C $(git -C "$C" rev-parse HEAD) helper_sha=$(shasum -a 256 "$H/stage4/pcca/PcacheProbe.java" | cut -c1-16) btm_sha=$(shasum -a 256 "$H/pcca.btm" | cut -c1-16) client_sha=$(shasum -a 256 "$H/pcca-client.py" | cut -c1-16) script_sha=$(shasum -a 256 "$0" | cut -c1-16)"
pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
rm -rf "$BIN/classes"; mkdir -p "$BIN/classes"
javac -d "$BIN/classes" -cp "$C/build/classes/main:$C/build/lib/jars/*" "$H/stage4/pcca/PcacheProbe.java" >> "$L/commands.log" 2>&1 || { log "ABORT: helper compile"; exit 1; }
( cd "$BIN/classes" && jar cf "$BIN/pcca-helper.jar" stage4 ) || { log "ABORT: helper jar"; exit 1; }
java -cp "$C/build/lib/jars/byteman-4.0.20.jar:$BIN/pcca-helper.jar:$C/build/classes/main:$C/build/lib/jars/*" org.jboss.byteman.check.TestScript "$H/pcca.btm" > "$L/btm-check.txt" 2>&1
grep -q 'TestScript: no errors' "$L/btm-check.txt" || { log "ABORT: Byteman rule check failed"; exit 1; }
log "helper jar built; rule type-checked: $(tail -1 "$L/btm-check.txt")"
CLIENT() { python3 "$H/pcca-client.py" "$@"; }

make_node() { # $1 = cap (MiB or default)
  rm -rf "$N"; mkdir -p "$N"/data "$N"/commitlog "$N"/hints "$N"/saved_caches "$N"/cdc_raw "$N"/logs
  cp -R "$C/conf" "$N/conf"
  local Y=$N/conf/cassandra.yaml
  grep -v -E '^(cluster_name|listen_address|rpc_address|hints_directory|commitlog_directory|saved_caches_directory|cdc_raw_directory|paxos_cache_size|paxos_variant):' "$C/conf/cassandra.yaml" > "$Y"
  cat >> "$Y" <<YAML
# --- stage-4 overrides (B3a/B3b, amendments C1/C2 of 2026-10-27) ---
cluster_name: 'pcache'
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
data_file_directories:
    - $N/data
commitlog_directory: $N/commitlog
hints_directory: $N/hints
saved_caches_directory: $N/saved_caches
cdc_raw_directory: $N/cdc_raw
YAML
  [ "$1" != default ] && echo "paxos_cache_size: ${1}MiB" >> "$Y"
  return 0
}
start_node() { # $1 = round dir
  ( cd "$C" && CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M \
    JVM_EXTRA_OPTS="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/pcca.btm,sys:$BIN/pcca-helper.jar -Dpcca.out=$1/probe.txt" \
    exec bin/cassandra -f > "$1/node-stdout.log" 2>&1 < /dev/null ) &
  P1=$!
  log "started node pid=$P1"
}
wait_up() {
  local i
  for i in $(seq 1 120); do
    kill -0 "$P1" 2>/dev/null || { log "node died during start"; return 1; }
    if [ "$(NT statusbinary 2>/dev/null)" = "running" ] && NT status 2>/dev/null | grep -q '^UN'; then log "node UN and binary running after ~$((i*2)) s"; return 0; fi
    sleep 2
  done
  return 1
}
reading() { # $1 = round dir, $2 = tag ; probe then histogram
  local T=$1 tag=$2 before after
  before=$(wc -l < "$T/probe.txt" 2>/dev/null || echo 0)
  NT getconcurrentviewbuilders > "$T/gcvb-$tag.txt" 2>&1
  after=$(wc -l < "$T/probe.txt" 2>/dev/null || echo 0)
  local line; line=$(tail -1 "$T/probe.txt" 2>/dev/null)
  echo "$tag,$line" >> "$T/probes-tagged.csv"
  jcmd "$JP" GC.class_histogram > "$T/histo-$tag.txt" 2>&1
  local nS nK tot
  nS=$(awk '$4=="org.apache.cassandra.service.paxos.PaxosState$Snapshot"{print $2}' "$T/histo-$tag.txt"); nS=${nS:-0}
  nK=$(awk '$4=="org.apache.cassandra.service.paxos.PaxosState$Key"{print $2}' "$T/histo-$tag.txt"); nK=${nK:-0}
  tot=$(awk '$1=="Total"{print $3}' "$T/histo-$tag.txt")
  log "[$tag] probe lines $before->$after: $line | histo n_S=$nS n_K=$nK total_bytes=$tot"
}

for CV in $CAPS; do
  T=$L/C$CV; mkdir -p "$T"
  log "===== cap=$CV ====="
  make_node "$CV"
  diff "$C/conf/cassandra.yaml" "$N/conf/cassandra.yaml" > "$T/yaml.diff"
  start_node "$T"
  if ! wait_up; then log "ROUND FAILED: node did not start"; tail -30 "$T/node-stdout.log" >> "$L/commands.log"; stop_node; continue; fi
  JP=$(pgrep -f "cassandra.logdir=$N/logs" | head -1); log "node java pid=$JP"
  grep -c 'Byteman' "$T/node-stdout.log" > /dev/null
  CLIENT settings > "$T/settings.json" 2>&1; log "settings: $(cat "$T/settings.json")"
  CLIENT schema > "$T/schema.json" 2>&1 || { log "ROUND FAILED: schema $(cat "$T/schema.json")"; stop_node; continue; }
  log "schema: $(cat "$T/schema.json")"
  reading "$T" baseline
  ok=1
  for j in $(seq 0 $((NCHUNK - 1))); do
    lo=$((j * CHUNK)); hi=$(((j + 1) * CHUNK))
    log "+ pcca-client.py lwt $lo $hi"
    CLIENT lwt $lo $hi > "$T/lwt-$hi.json" 2> "$T/lwt-$hi.err"; rc=$?
    log "  rc=$rc $(cat "$T/lwt-$hi.json")"
    [ $rc = 0 ] || ok=0
    reading "$T" "i$hi"
  done
  log "idle 30 s"; sleep 30
  reading "$T" final
  run NT flush
  jcmd "$JP" GC.class_histogram > "$T/histo-flushed.txt" 2>&1
  log "after flush: total_bytes=$(awk '$1=="Total"{print $3}' "$T/histo-flushed.txt")"
  grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v -E 'Small commitlog volume|swap|Unable to lock JVM memory|jemalloc|OpenJDK|JMX is not enabled|Non-UTC|Using AWS|dynamic_snitch' | head -50 > "$T/system-errwarn.txt"
  cp "$N/logs/system.log" "$T/system.log" 2>/dev/null
  log "round ok=$ok; system.log ERROR/WARN lines kept: $(wc -l < "$T/system-errwarn.txt" | tr -d ' ')"
  stop_node
  pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' >/dev/null && log "WARNING: daemon still present" || log "no Cassandra daemon left"
  du -sk "$N" > "$T/node-du.txt"; rm -rf "$N"
done
log "cluster-run $LABEL done; clone git status lines: $(git -C "$C" status --short | wc -l | tr -d ' ')"
