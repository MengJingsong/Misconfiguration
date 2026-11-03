#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-24) of memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous, one run.
# usage: cluster-run.sh <label> <memtable_heap_space: e.g. 64MiB | unset> [heap_buffers | offheap_objects <memtable_offheap_space>]
# Needs: source ~/Library/Caches/stage4/env.sh. Node from clone $C (default $W/cassandra-run2), data under $W/node-mhs (wiped
# before and after), logs under $W/logs/memtable_heap_space-applySimpleConfig/cluster/<label>/. One node, 127.0.0.1.
set -uo pipefail
LABEL=$1; HS=$2; ALLOC=${3:-heap_buffers}; OFFS=${4:-}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run2}; N=$W/node-mhs
L=$W/logs/memtable_heap_space-applySimpleConfig/cluster/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
x() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local r=$?; log "rc=$r"; return $r; }
ps -eo command | grep -q '[C]assandraDaemon' && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
log "run $LABEL memtable_heap_space=$HS allocation=$ALLOC offheap=$OFFS clone=$(git -C "$C" rev-parse HEAD)"
df -h "$W" | tail -1 >> "$L/commands.log"
# javac the sampler
mkdir -p "$W/harness-bin"; x javac -d "$W/harness-bin" "$H/Sampler.java" || exit 1
# node directories and configuration (B3a)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(memtable_allocation_type|memtable_heap_space|memtable_offheap_space|concurrent_compactors|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "memtable_allocation_type: $ALLOC"; echo "concurrent_compactors: 1"
  [ "$HS" = unset ] || echo "memtable_heap_space: $HS"
  [ -n "$OFFS" ] && echo "memtable_offheap_space: $OFFS"; } >> "$Y"
tail -16 "$Y" > "$L/yaml-overrides.txt"
# start the node (B3e step 1)
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
stop_node() {
  log "stopping node"; touch "$L/stop"; [ -n "${JPID:-}" ] && kill "$JPID" 2>/dev/null
  (cd "$C" && bin/nodetool drain) >> "$L/commands.log" 2>&1; log "drain rc=$?"
  kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
  kill -9 "$NPID" 2>/dev/null
  sleep 2; if ps -eo command | grep -q '[C]assandraDaemon'; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi; }
trap stop_node EXIT
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DPID=$(pgrep -f 'org.apache.cassandra.service.CassandraDaemon' | head -1); log "node UN, statusbinary running; daemon pid $DPID"
grep -E 'Global memtable on-heap threshold|Global memtable off-heap threshold|MemtableHeapSpace|Heap size' "$N/logs/system.log" | head -5 > "$L/startup-threshold.txt"
cat "$L/startup-threshold.txt" >> "$L/commands.log"
SL0=$(wc -c < "$N/logs/system.log")
# cross-check (B3d amended): one nodetool sjk read of the gauge at start, timed
t0=$(date +%s); (cd "$C" && bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize" -mg -f Value) > "$L/sjk-start.txt" 2>&1; log "sjk start took $(( $(date +%s) - t0 )) s: $(tail -1 "$L/sjk-start.txt")"
# samplers (B3e step 2)
java -cp "$W/harness-bin" Sampler 7199 "$L/samples.csv" "$L/stop" > "$L/sampler.err" 2>&1 & SPID=$!
JPID=
log "sampler pid $SPID (old gen read by the sampler; jstat cannot attach: -XX:+PerfDisableSharedMem, runbook fix 2026-10-24)"
sleep 3
# workload (B3c, as written)
log "+ tools/bin/cassandra-stress write n=3000000 cl=ONE -col n=FIXED(5) size=FIXED(200) -rate threads=64 -schema replication(factor=1)"
s0=$(date +%s)
(cd "$C" && tools/bin/cassandra-stress write n=3000000 cl=ONE -col "n=FIXED(5)" "size=FIXED(200)" -rate threads=64 -schema "replication(factor=1)") > "$L/stress.log" 2>&1
log "stress rc=$? after $(( $(date +%s) - s0 )) s"
sleep 10
t0=$(date +%s); (cd "$C" && bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize" -mg -f Value) > "$L/sjk-end.txt" 2>&1; log "sjk end took $(( $(date +%s) - t0 )) s: $(tail -1 "$L/sjk-end.txt")"
(cd "$C" && bin/nodetool sjk mx -b "org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation" -mg -f Count) > "$L/sjk-blocked-end.txt" 2>&1
touch "$L/stop"; wait "$SPID" 2>/dev/null; kill "$JPID" 2>/dev/null; JPID=
# log excerpts written after the start offset
tail -c +$((SL0+1)) "$N/logs/system.log" > "$L/system-after-start.log"
grep -E 'Flushing largest|Enqueuing flush' "$L/system-after-start.log" > "$L/flush-lines.txt"
grep -E '^(ERROR|WARN)' "$L/system-after-start.log" | grep -v -i 'Small cdc volume\|jemalloc\|swap\|max map count' | head -200 > "$L/error-warn.txt"
grep -c 'java.lang.OutOfMemoryError' "$N/logs/system.log" > "$L/oom-count.txt"
cp "$N/logs/system.log" "$L/system.log"; cp "$N/logs/gc.log"* "$L/" 2>/dev/null
trap - EXIT; stop_node
du -sh "$N/data" >> "$L/commands.log" 2>&1
rm -rf "$N"; log "node dir wiped"
python3 -I "$H/summarize.py" "$L" | tee "$L/summary.txt"
