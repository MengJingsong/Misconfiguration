#!/usr/bin/env bash
# Stage-4 harness: memtable_heap_space-LeafBuilder-allocated--autonomous, cluster tier (B3 as amended C1-C8, 2026-10-27), one run.
# usage: cluster-run.sh <label> <V0|V1> <memtable_heap_space: 64MiB | 256MiB | unset> <single|batch> <n_main> <n_tail>
# Node from $W/cassandra-run61 (V0) or $W/cassandra-run61v1 (V1); data under $W/node-mhslb (wiped before and after);
# logs under $W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/cluster/<label>/. One node, 127.0.0.1.
# Node mechanics (start, wait, stop) adapted from harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/cluster-run.sh.
# Re-run (amendment of 2026-10-27 after run 1, authorised by the user): env C0/C1 select the V0/V1 clones (default run 1's) and
# LBASE the log folder (<LBASE>/<label>; default .../cluster).
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
LABEL=$1; VAR=$2; HS=$3; MODE=$4; NMAIN=$5; NTAIL=$6
H=$(cd "$(dirname "$0")" && pwd)
case $VAR in V0) C=${C0:-$W/cassandra-run61};; V1) C=${C1:-$W/cassandra-run61v1};; *) echo "bad variant"; exit 2;; esac
N=$W/node-mhslb; B=$W/harness-bin-mhslb
L=${LBASE:-$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/cluster}/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
SUM=$L/summary.txt; : > "$SUM"
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
x() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local r=$?; log "rc=$r"; return $r; }
say() { echo "$*" | tee -a "$SUM" >> "$L/commands.log"; }
ps -eo command | grep -q '[C]assandraDaemon' && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
say "RUN label=$LABEL variant=$VAR memtable_heap_space=$HS mode=$MODE n_main=$NMAIN n_tail=$NTAIL clone=$C $(git -C "$C" rev-parse --short HEAD)"
say "BTREE 2683=[$(sed -n 2683p $C/src/java/org/apache/cassandra/utils/btree/BTree.java | sed 's/^ *//')] 2736=[$(sed -n 2736p $C/src/java/org/apache/cassandra/utils/btree/BTree.java | sed 's/^ *//')]"
df -h "$W" | tail -1 >> "$L/commands.log"
mkdir -p "$B"; x javac -d "$B" "$H/Sampler.java" || exit 1
# node directories and configuration (B3a as amended C1)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(memtable_allocation_type|memtable_heap_space|memtable_cleanup_threshold|memtable_flush_writers|commitlog_segment_size|concurrent_writes|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "memtable_allocation_type: unslabbed_heap_buffers"
  [ "$HS" = unset ] || echo "memtable_heap_space: $HS"
  echo "memtable_cleanup_threshold: 0.5"; echo "memtable_flush_writers: 1"
  echo "commitlog_segment_size: 32MiB"; echo "concurrent_writes: 32"; } >> "$Y"
tail -16 "$Y" > "$L/yaml-overrides.txt"
BM="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/node-counters.btm"
log "+ MAX_HEAP_SIZE=2G CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs JVM_EXTRA_OPTS=\"$BM\" bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" JVM_EXTRA_OPTS="$BM" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
SPID=
stop_node() {
  [ "${BASH_SUBSHELL:-0}" = 0 ] || return 0
  log "stopping node"; touch "$L/stop"; [ -n "$SPID" ] && kill "$SPID" 2>/dev/null
  (cd "$C" && bin/nodetool drain) >> "$L/commands.log" 2>&1; log "drain rc=$?"
  kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
  kill -9 "$NPID" 2>/dev/null
  sleep 2; if ps -eo command | grep -q '[C]assandraDaemon'; then log "WARNING: Cassandra daemon still running"; else log "no Cassandra daemon left"; fi; }
trap stop_node EXIT
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DPID=$(pgrep -f 'org.apache.cassandra.service.Cassandra[D]aemon' | head -1); log "node UN, statusbinary running; daemon pid $DPID"
say "START $(grep -m1 -o 'Global memtable on-heap threshold is enabled at [0-9A-Za-z]*' "$N/logs/system.log") | $(grep -m1 -o 'memtable_cleanup_threshold=[^;,]*' "$N/logs/system.log") | $(grep -m1 -o 'memtable_flush_writers=[^;,]*' "$N/logs/system.log") | $(grep -m1 -o 'memtable_allocation_type=[^;,]*' "$N/logs/system.log") heap: $(grep -m1 -o 'Heap size: [^,]*, [^ ]*' "$N/logs/system.log")"
SL0=$(wc -c < "$N/logs/system.log")
java -cp "$B" Sampler loop 7199 "$L/samples.csv" "$L/stop" 2000 > "$L/sampler.err" 2>&1 & SPID=$!
log "sampler pid $SPID (2 s)"
sleep 3
wait_idle() {   # flush writer and post-flush idle twice in a row (max 600 s)
  local n=0
  for i in $(seq 1 300); do
    local tp; tp=$(cd "$C" && bin/nodetool tpstats 2>/dev/null | awk '$1=="MemtableFlushWriter"||$1=="MemtablePostFlush"||$1=="MemtableReclaimMemory"{a+=$2; p+=$3} END{print a+p}')
    if [ "$tp" = 0 ]; then n=$((n+1)); [ $n -ge 2 ] && { log "idle after $((i*2)) s"; return 0; }; else n=0; fi
    sleep 2
  done
  log "WARNING: not idle after 600 s"; return 1; }
hist() {   # hist <name>: live-object class histogram (forces a full GC); total bytes in HIST line
  jcmd "$DPID" GC.class_histogram > "$L/hist-$1.txt" 2>&1
  local tot; tot=$(awk '$1=="Total"{print $3}' "$L/hist-$1.txt")
  say "HIST $1 total_bytes=$tot epoch_ms=$(python3 -c 'import time;print(int(time.time()*1000))')"; }
once() { java -cp "$B" Sampler once 7199 2>>"$L/sampler.err" | tee -a "$L/once.txt"; }
stress() {   # stress <tag> <n>
  log "+ tools/bin/cassandra-stress user profile=$H/wide-$MODE.yaml ops(insert=1) n=$2 cl=ONE no-warmup -rate threads=32 -node 127.0.0.1 > stress-$1.log"
  local s0; s0=$(date +%s)
  (cd "$C" && tools/bin/cassandra-stress user profile="$H/wide-$MODE.yaml" "ops(insert=1)" n=$2 cl=ONE no-warmup -rate threads=32 -node 127.0.0.1) > "$L/stress-$1.log" 2>&1 < /dev/null
  local rc=$?
  say "STRESS $1 n=$2 rc=$rc secs=$(( $(date +%s) - s0 )) $(grep -E '^(Op rate|Partition rate|Row rate|Total partitions|Total errors|Total operation time)' "$L/stress-$1.log" | tr -s ' ' | tr '\n' ';')"
  grep -A30 '^Results:' "$L/stress-$1.log" > "$L/stress-$1-results.txt"; }
# main workload (B3c as amended C3)
stress main "$NMAIN"
wait_idle
say "AFTERMAIN $(once)"
# empty the memtable, then the idle control (C5): histogram, flush of the (empty) memtable, histogram
x bash -c "cd '$C' && bin/nodetool flush ks t"; wait_idle
hist idle1; x bash -c "cd '$C' && bin/nodetool flush ks t"; wait_idle; hist idle2
say "BEFORETAIL $(once)"
# tail: a fresh memtable filled to about 0.25 x limit, no switch expected (C5)
stress tail "$NTAIL"
wait_idle
sleep 4
say "ENDTAIL $(once)"
hist end1
x bash -c "cd '$C' && bin/nodetool flush ks t"; wait_idle
hist end2
say "AFTERFLUSH $(once)"
touch "$L/stop"; wait "$SPID" 2>/dev/null; SPID=
# log excerpts written after the start offset
tail -c +$((SL0+1)) "$N/logs/system.log" > "$L/system-after-start.log"
grep -E 'Flushing largest' "$L/system-after-start.log" > "$L/flush-largest-lines.txt"
grep -E 'Enqueuing flush of (ks\.)?t\b|Enqueuing flush of t:' "$L/system-after-start.log" > "$L/enqueue-t-lines.txt"
grep -E '^(ERROR|WARN)' "$L/system-after-start.log" | head -200 > "$L/error-warn.txt"
grep -c 'java.lang.OutOfMemoryError' "$N/logs/system.log" > "$L/oom-count.txt"
grep '^STAGE4BM' "$L/node.out" > "$L/bm-lines.txt"
cp "$N/logs/system.log" "$L/system.log"; cp "$N/logs/gc.log"* "$L/" 2>/dev/null
say "BM $(wc -l < "$L/bm-lines.txt" | tr -d ' ') switch lines; last: $(tail -1 "$L/bm-lines.txt")"
say "FLUSHLARGEST $(wc -l < "$L/flush-largest-lines.txt" | tr -d ' ') lines; errors/warns $(wc -l < "$L/error-warn.txt" | tr -d ' '); OOM $(cat "$L/oom-count.txt")"
trap - EXIT; stop_node
du -sh "$N/data" >> "$L/commands.log" 2>&1
rm -rf "$N"; log "node dir wiped"
say "END $(date '+%F %T')"
