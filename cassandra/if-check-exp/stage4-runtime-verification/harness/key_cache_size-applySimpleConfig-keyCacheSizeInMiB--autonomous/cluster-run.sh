#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-25) of key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous: one node lifetime.
# usage: cluster-run.sh <label> <value: 8MiB | 64MiB | auto | ...>
#   start node (MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M), read back the capacity line, stress write NW partitions, flush, compact,
#   SSTable count/format, baseline sample + histogram, B3h control read (NC partitions, seq 1..NC), main read (NR partitions,
#   seq 1..NR), final sample + histogram, stop, wipe.  KeyCacheSampler (JMX, every 2 s) runs from baseline to the end.
# Env: C (clone, default $W/cassandra-run11), OUT (log root), NW (2000000), NR (2000000), NC (20000).
# Node data under ${KCS_NODE:-$W/node-kcs} (wiped before and after). One node, 127.0.0.1. Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
LABEL=$1; VAL=$2
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run11}; N=${KCS_NODE:-$W/node-kcs}   # KCS_NODE: cluster re-run 2026-10-25 (H4)
OUT=${OUT:-$W/logs/key_cache_size-applySimpleConfig/cluster}; NW=${NW:-2000000}; NR=${NR:-2000000}; NC=${NC:-20000}
L=$OUT/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "run $LABEL key_cache_size=$VAL NW=$NW NR=$NR NC=$NC clone=$(git -C "$C" rev-parse HEAD) $(date +%s)"
df -h "$W" | tail -1 >> "$L/commands.log"
mkdir -p "$W/harness-bin-kcs"; javac -d "$W/harness-bin-kcs" "$H/KeyCacheSampler.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac KeyCacheSampler"; exit 1; }
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(key_cache_size|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
  | grep -v -E '^    - /var/lib/cassandra/data$' > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  if [ "$VAL" = auto ]; then echo "key_cache_size:"; else echo "key_cache_size: $VAL"; fi; } >> "$Y"
tail -9 "$Y" > "$L/yaml-overrides.txt"
diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-diff.txt"
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
SPID=""
stop_node() {
  log "stopping node"
  touch "$L/stop"; [ -n "$SPID" ] && { for i in $(seq 1 10); do kill -0 "$SPID" 2>/dev/null || break; sleep 1; done; kill "$SPID" 2>/dev/null; }
  if kill -0 "$NPID" 2>/dev/null; then
    ( cd "$C" && bin/nodetool drain ) >> "$L/commands.log" 2>&1 & DRP=$!
    for i in $(seq 1 90); do kill -0 "$DRP" 2>/dev/null || break; sleep 1; done; kill "$DRP" 2>/dev/null; log "drain done or bounded"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill -9 "$NPID" 2>/dev/null
  fi
  pkill -9 -f 'org.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  pkill -9 -f 'org.apache.cassandra.stress.Stress' 2>/dev/null
  sleep 2; if pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"
  du -sh "$N/data" "$N/commitlog" "$N/saved_caches" >> "$L/commands.log" 2>&1
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DPID=$(pgrep -f org.apache.cassandra.service.CassandraDaemon | head -1); log "node UN, statusbinary running; daemon pid $DPID"
RB=$(grep -o 'Initializing key cache with capacity of [0-9]* MiBs' "$N/logs/system.log" | head -1)
note "READBACK $RB"
case $VAL in auto) EXP=100;; *) EXP=${VAL%MiB};; esac
[ "$RB" = "Initializing key cache with capacity of $EXP MiBs" ] || { note "READBACK MISMATCH expected $EXP MiB"; exit 1; }
stress() { local tag=$1; shift; local s0=$(date +%s); log "+ tools/bin/cassandra-stress $*"
  (cd "$C" && tools/bin/cassandra-stress "$@") > "$L/stress-$tag.log" 2>&1; local rc=$?
  note "STRESS $tag rc=$rc secs=$(( $(date +%s) - s0 )) $(grep -E '^Total partitions' "$L/stress-$tag.log" | tr -s ' ' | head -1) | $(grep -E '^Total errors' "$L/stress-$tag.log" | tr -s ' ' | head -1)"; }
ntool() { (cd "$C" && bin/nodetool "$@") >> "$L/commands.log" 2>&1; log "nodetool $* rc=$?"; }
histo() { jmap -histo:live "$DPID" > "$L/histo-$1.txt" 2>&1; jcmd "$DPID" GC.heap_info > "$L/heapinfo-$1.txt" 2>&1
  local tot k r; tot=$(grep -E '^Total' "$L/histo-$1.txt" | tr -s ' '); k=$(grep -E ' org\.apache\.cassandra\.cache\.KeyCacheKey$' "$L/histo-$1.txt" | tr -s ' ')
  r=$(grep -E ' org\.apache\.cassandra\.io\.sstable\.format\.big\.RowIndexEntry$' "$L/histo-$1.txt" | tr -s ' ')
  note "HISTO $1 total:$tot | KeyCacheKey:${k:- none} | RowIndexEntry:${r:- none}"
  grep -E 'KeyCacheKey|RowIndexEntry' "$L/histo-$1.txt" > "$L/histo-excerpt-$1.txt"; }
info() { (cd "$C" && bin/nodetool info 2>/dev/null) | grep 'Key Cache' | sed "s/^/INFO $1: /" | tee -a "$L/summary.txt"; }
phase() { echo "$1" > "$L/phase"; log "phase $1"; }
# B3c workload (amended): write, flush, compact
stress write write n=$NW -rate threads=50 -node 127.0.0.1
ntool flush keyspace1
ntool compact keyspace1
( cd "$C" && bin/nodetool tablestats keyspace1.standard1 ) > "$L/tablestats-after-compact.txt" 2>&1
find "$N/data" -name '*-Data.db' | sed "s#^$N/data/##" | sort > "$L/sstables-list.txt"   # shakedown fix H2: raw list
note "SSTABLES $(grep -E 'SSTable count' "$L/tablestats-after-compact.txt" | tr -s ' ' | head -1) | files: $(find "$N/data/keyspace1" -name '*-Data.db' | sed 's#.*/##' | tr '\n' ' ')"
note "SSTABLE-FORMAT-ALL-DATA $(find "$N/data" -name '*-Data.db' | sed -E 's#.*/[a-z]+-[0-9a-z_]+-([a-z]+)-Data.db#\1#' | sort | uniq -c | tr -s ' ' | tr '\n' ';')"
phase baseline
java -cp "$W/harness-bin-kcs" KeyCacheSampler 7199 "$L/samples.csv" "$L/phase" "$L/stop" > "$L/sampler.err" 2>&1 & SPID=$!
sleep 6
info baseline
histo 0-baseline
phase control-read
stress control read n=$NC no-warmup -pop seq=1..$NC -rate threads=50 -node 127.0.0.1
phase control-done; sleep 6
info control
phase main-read
stress main read n=$NR no-warmup -pop seq=1..$NR -rate threads=50 -node 127.0.0.1
phase main-done; sleep 6
info final
histo 1-end
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -50 > "$L/error-warn.txt"
note "ERROR/WARN lines: $(wc -l < "$L/error-warn.txt" | tr -d ' '); OOM: $(grep -c "java.lang.OutOfMemoryError" "$N/logs/system.log")"
trap - EXIT; stop_node; finish
