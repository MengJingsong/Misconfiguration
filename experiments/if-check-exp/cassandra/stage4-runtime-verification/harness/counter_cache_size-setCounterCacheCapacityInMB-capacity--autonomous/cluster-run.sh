#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-27) of counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous.
# Structure adapted from harness/key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous/cluster-run.sh (key cache -> counter cache,
# read passes -> counter_write passes, no flush/compact); CounterCacheSampler.java copied unchanged from the
# counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous harness.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh <label>
#   env: NW (400000), VALUES ("256 32 16 8"; the first is the unbounded control), SHRINK (8), YAML (16), C (clone), NODE.
#   shakedown: NW=40000 VALUES="64 4 2 1" SHRINK=1 YAML=2 cluster-run.sh shake
# Lifetime 1 (yaml counter_cache_size: 64MiB): per C: phase C-set, invalidatecountercache, setcachecapacity 0 0 C; phase C-write,
#   stress counter_write; phase C-done, 6 s, GC.run + live class histogram. After the first pass the shrink step (phase shrink-set,
#   setcachecapacity 0 0 SHRINK without invalidation, phase shrink, 7 s).
# Lifetime 2 (yaml counter_cache_size: <YAML>MiB, same data): invalidatecountercache, counter_write, histogram.
# JMX sampler (2 s) and `nodetool info` (10 s) run through each lifetime.
set -uo pipefail
LABEL=$1
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run46}; N=${NODE:-$W/node-ccr46}
NW=${NW:-400000}; VALUES=${VALUES:-256 32 16 8}; SHRINK=${SHRINK:-8}; YAML=${YAML:-16}
L=$W/logs/counter_cache_size-setCounterCacheCapacityInMB/cluster-$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
DPAT='org.apache.cassandra.service.Cassandra[D]aemon'; SPAT='org.apache.cassandra.stress.Stres[s]'
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a node is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "run $LABEL NW=$NW VALUES=[$VALUES] SHRINK=$SHRINK YAML=$YAML clone=$(git -C "$C" rev-parse HEAD) start_epoch=$(date +%s) harness=$(cat "$H"/cluster-run.sh "$H"/CounterCacheSampler.java | shasum -a 256 | cut -c1-16)"
df -h "$W" | tail -1 >> "$L/commands.log"
mkdir -p "$W/harness-bin-ccr"; javac -d "$W/harness-bin-ccr" "$H/CounterCacheSampler.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac"; exit 1; }
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
mkyaml() {   # $1 = counter_cache_size value
  grep -v -E '^(key_cache_size|counter_cache_save_period|row_cache_size|counter_cache_size|file_cache_enabled|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
    | grep -v -E '^    - /var/lib/cassandra/data$' > "$Y"
  { echo; echo "# stage-4 overrides ($LABEL)"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    echo "counter_cache_size: $1"; echo "counter_cache_save_period: 0s"; echo "key_cache_size: 0MiB"; echo "row_cache_size: 0MiB"
    echo "file_cache_enabled: false"; } >> "$Y"; }
NPID=""; SPID=""; IPID=""; DPID=""
start_node() {   # $1 = tag, $2 = expected MiB
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=200M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f  ($1)"
  local off=0; [ -f "$N/logs/system.log" ] && off=$(wc -c < "$N/logs/system.log")
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=200M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node-$1.out" 2>&1 < /dev/null &
  NPID=$!; local ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || { note "ABORT: node died during start"; return 1; }
    if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || { note "ABORT: node not UN/running in 360 s"; return 1; }
  DPID=$(pgrep -f "$DPAT" | head -1); log "node $1 up, pid $DPID"
  local rb; rb=$(tail -c +$((off+1)) "$N/logs/system.log" | grep -o 'Initializing counter cache with capacity of [0-9]* MiBs' | head -1)
  note "READBACK $1 $rb"
  [ "$rb" = "Initializing counter cache with capacity of $2 MiBs" ] || { note "READBACK MISMATCH $1 expected $2"; return 1; }
  ( cd "$C" && bin/nodetool info 2>/dev/null ) | grep -E 'Cache' | sed "s/^/INFO $1-start: /" >> "$L/info.txt"
  ps -o command= -p "$DPID" | tr ' ' '\n' | grep -E '^-Xm[sx]' | tr '\n' ' ' | sed "s/^/JVM $1: /" >> "$L/summary.txt"; echo >> "$L/summary.txt"
}
start_instruments() {   # $1 = csv tag
  rm -f "$L/stop"
  java -cp "$W/harness-bin-ccr" CounterCacheSampler 7199 "$L/samples-$1.csv" "$L/phase" "$L/stop" > "$L/sampler-$1.err" 2>&1 & SPID=$!
  ( while [ ! -f "$L/stop" ]; do echo "$(date +%s) $(cat "$L/phase" 2>/dev/null) $( (cd "$C" && bin/nodetool info 2>/dev/null) | grep '^Counter Cache')" >> "$L/info-10s-$1.txt"; sleep 10; done ) & IPID=$!
}
stop_instruments() {
  touch "$L/stop"; for i in $(seq 1 15); do kill -0 "$SPID" 2>/dev/null || break; sleep 1; done; kill "$SPID" 2>/dev/null
  for i in $(seq 1 15); do kill -0 "$IPID" 2>/dev/null || break; sleep 1; done; kill "$IPID" 2>/dev/null; SPID=""; IPID=""; }
stop_node() {   # $1 = tag
  [ -n "$SPID" ] && stop_instruments
  if [ -n "$NPID" ] && kill -0 "$NPID" 2>/dev/null; then
    ( cd "$C" && bin/nodetool info 2>/dev/null ) | grep -E 'Cache' | sed "s/^/INFO $1-end: /" >> "$L/info.txt"
    ( cd "$C" && bin/nodetool drain ) >> "$L/commands.log" 2>&1 & local d=$!
    for i in $(seq 1 90); do kill -0 "$d" 2>/dev/null || break; sleep 1; done; kill "$d" 2>/dev/null; log "drain done ($1)"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done; kill -9 "$NPID" 2>/dev/null
  fi
  pkill -9 -f "$DPAT" 2>/dev/null; pkill -9 -f "$SPAT" 2>/dev/null; sleep 2
  pgrep -f "$DPAT" >/dev/null && log "WARNING: node still running" || log "no node left ($1)"; NPID=""; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"
  du -sh "$N/data" >> "$L/commands.log" 2>&1; rm -rf "$N"; log "node dir removed"; }
trap 'stop_node trap; finish' EXIT
phase() { echo "$1" > "$L/phase"; log "phase $1"; }
ntool() { (cd "$C" && bin/nodetool "$@") >> "$L/commands.log" 2>&1; local rc=$?; log "nodetool $* rc=$rc"; return $rc; }
stress() { local tag=$1; shift; local s0=$(date +%s); log "+ tools/bin/cassandra-stress $*"
  (cd "$C" && tools/bin/cassandra-stress "$@") > "$L/stress-$tag.log" 2>&1; local rc=$?
  note "STRESS $tag rc=$rc secs=$(( $(date +%s) - s0 )) $(grep -E '^Total partitions' "$L/stress-$tag.log" | tr -s ' ' | head -1) | $(grep -E '^Total errors' "$L/stress-$tag.log" | tr -s ' ' | head -1)"; }
histo() { local g; g=$(jcmd "$DPID" GC.run 2>&1 | tail -1); log "GC.run: $g"
  jcmd "$DPID" GC.class_histogram > "$L/histo-$1.txt" 2>&1
  note "HISTO $1 $(grep -E ' org\.apache\.cassandra\.cache\.CounterCacheKey$' "$L/histo-$1.txt" | tr -s ' ') | $(grep -E ' org\.apache\.cassandra\.db\.ClockAndCount$' "$L/histo-$1.txt" | tr -s ' ') | $(grep -E ' com\.github\.benmanes\.caffeine\.cache\.PSMW$' "$L/histo-$1.txt" | tr -s ' ')"; }
WRITE="counter_write n=$NW cl=ONE -pop seq=1..$NW -rate threads=50 -node 127.0.0.1"

# ---- lifetime 1: yaml 64 MiB, runtime sets
mkyaml 64MiB; tail -12 "$Y" > "$L/yaml-tail-1.txt"
start_node L1 64 || exit 1
phase baseline; start_instruments L1; sleep 6
first=1
for c in $VALUES; do
  phase "$c-set"; ntool invalidatecountercache; ntool setcachecapacity 0 0 "$c"
  phase "$c-write"; stress "write-$c" $WRITE
  phase "$c-done"; sleep 6; histo "$c"
  if [ $first = 1 ]; then
    first=0
    phase shrink-set; ntool setcachecapacity 0 0 "$SHRINK"
    phase shrink; sleep 7
  fi
done
stop_node L1
# ---- lifetime 2: yaml YAML MiB, same data
mkyaml ${YAML}MiB; tail -12 "$Y" > "$L/yaml-tail-2.txt"
start_node L2 "$YAML" || exit 1
phase "y$YAML-baseline"; start_instruments L2; sleep 6
phase "y$YAML-set"; ntool invalidatecountercache
phase "y$YAML-write"; stress "write-y$YAML" $WRITE
phase "y$YAML-done"; sleep 6; histo "y$YAML"
stop_node L2
note "ERROR lines in system.log: $(grep -c '^ERROR' "$N/logs/system.log") ; java.lang.OutOfMemoryError: $(grep -c 'java.lang.OutOfMemoryError' "$N/logs/system.log")"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -40 > "$L/error-warn.txt"
trap - EXIT; finish
pgrep -f "$SPAT" >/dev/null && log "WARNING: stress left" || log "no stress left"
log "cluster-run $LABEL done"
