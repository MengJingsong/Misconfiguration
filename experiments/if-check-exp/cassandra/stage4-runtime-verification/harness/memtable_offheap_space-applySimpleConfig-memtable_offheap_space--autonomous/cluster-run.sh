#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-24) of memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous, one run.
# usage: cluster-run.sh <label> <memtable_allocation_type> <memtable_offheap_space: e.g. 64MiB | 0MiB | unset> [normal | stall]
#   normal: B3c stress n=3000000, wait up to 360 s for startup.
#   stall : case (c) of B3e amended — startup judged at 120 s (thread dump + kill -9 if not up); else stress duration=60s under 180 s,
#           thread dump 60 s into stress, drain bounded to 60 s, then kill -9.
# Needs: source ~/Library/Caches/stage4/env.sh. Node from clone $C (default $W/cassandra-run3), data under $W/node-mos (wiped before and
# after), logs under $W/logs/memtable_offheap_space-applySimpleConfig/cluster/<label>/. One node, 127.0.0.1. memtable_heap_space 512MiB.
set -uo pipefail
LABEL=$1; ALLOC=$2; OFFS=$3; MODE=${4:-normal}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run3}; N=$W/node-mos; HB=$W/harness-bin-mos
L=$W/logs/memtable_offheap_space-applySimpleConfig/cluster/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
x() { log "+ $*"; "$@" >> "$L/commands.log" 2>&1; local r=$?; log "rc=$r"; return $r; }
nt() { (cd "$C" && timeout 20 bin/nodetool "$@"); }
ps -eo command | grep -q '[C]assandraDaemon' && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
log "run $LABEL allocation=$ALLOC memtable_offheap_space=$OFFS mode=$MODE memtable_heap_space=512MiB clone=$(git -C "$C" rev-parse HEAD)"
df -h "$W" | tail -1 >> "$L/commands.log"
mkdir -p "$HB"; x javac -d "$HB" "$H/Sampler.java" || exit 1
# node directories and configuration (B3a)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(memtable_allocation_type|memtable_heap_space|memtable_offheap_space|concurrent_compactors|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "memtable_allocation_type: $ALLOC"; echo "concurrent_compactors: 1"; echo "memtable_heap_space: 512MiB"
  [ "$OFFS" = unset ] || echo "memtable_offheap_space: $OFFS"; } >> "$Y"
tail -14 "$Y" > "$L/yaml-overrides.txt"
echo "-XX:NativeMemoryTracking=summary" >> "$N/conf/jvm-server.options"
grep -n 'NativeMemoryTracking\|AlwaysPreTouch\|PerfDisableSharedMem' "$N/conf/jvm-server.options" >> "$L/yaml-overrides.txt"
# start the node (B3e)
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
T0=$(date +%s)
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
SPID=; RPID=; MPID=; TPID=
dpid() { pgrep -f 'org.apache.cassandra.service.CassandraDaemon' | head -1; }
stop_node() {
  log "stopping node"; touch "$L/stop"
  for p in $SPID $RPID $MPID $TPID; do kill "$p" 2>/dev/null; done
  if kill -0 "$NPID" 2>/dev/null; then
    (cd "$C" && timeout ${DRAIN_LIMIT:-120} bin/nodetool drain) >> "$L/commands.log" 2>&1; log "drain rc=$?"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
  fi
  D=$(dpid); [ -n "$D" ] && { log "kill -9 daemon $D"; kill -9 "$D"; }
  kill -9 "$NPID" 2>/dev/null
  pkill -9 -f cassandra-stress 2>/dev/null
  sleep 2; if ps -eo command | grep -q '[C]assandraDaemon'; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi
  if pgrep -f cassandra-stress >/dev/null; then log "WARNING: cassandra-stress still running"; else log "no cassandra-stress left"; fi; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"; cp "$N/logs/gc.log"* "$L/" 2>/dev/null
  grep -E 'Global memtable on-heap threshold|Global memtable off-heap threshold|Memtables allocating' "$L/system.log" 2>/dev/null | head -5 > "$L/startup-threshold.txt"
  du -sh "$N/data" >> "$L/commands.log" 2>&1
  rm -rf "$N"; log "node dir wiped"
  python3 -I "$H/summarize.py" "$L" | tee "$L/summary.txt"; }
trap 'stop_node; finish' EXIT
LIMIT=360; [ "$MODE" = stall ] && LIMIT=120
ok=0
while [ $(( $(date +%s) - T0 )) -lt $LIMIT ]; do
  kill -0 "$NPID" 2>/dev/null || { log "node died during start"; break; }
  if nt status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
echo "startup_complete=$ok after $(( $(date +%s) - T0 )) s" > "$L/startup.txt"; log "$(cat "$L/startup.txt")"
DPID=$(dpid); log "daemon pid ${DPID:-none}"
if [ $ok != 1 ]; then
  if [ "$MODE" = stall ] && [ -n "$DPID" ]; then
    jcmd "$DPID" Thread.print > "$L/threaddump.txt" 2>&1; log "thread dump at $(( $(date +%s) - T0 )) s: $(grep -c 'MemtableAllocator\$SubAllocator.allocate' "$L/threaddump.txt") frames in SubAllocator.allocate"
    ps -o rss= -p "$DPID" > "$L/rss-at-dump.txt"
    log "kill -9 $DPID (B3e amended: startup not complete in 120 s)"; kill -9 "$DPID"
    exit 0
  fi
  log "ABORT: node not UN/running within $LIMIT s"; exit 1
fi
SL0=$(wc -c < "$N/logs/system.log")
t0=$(date +%s); nt sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize" -mg -f Value > "$L/sjk-start.txt" 2>&1; log "sjk start took $(( $(date +%s) - t0 )) s: $(tail -1 "$L/sjk-start.txt")"
# samplers (B3d amended): JMX every 1 s, RSS every 2 s, NMT every 10 s
java -cp "$HB" Sampler 7199 "$L/samples.csv" "$L/stop" > "$L/sampler.err" 2>&1 & SPID=$!
( echo "epoch_s,rss_kb"; while [ ! -e "$L/stop" ]; do echo "$(date +%s),$(ps -o rss= -p "$DPID" | tr -d ' ')"; sleep 2; done ) > "$L/rss.csv" & RPID=$!
( while [ ! -e "$L/stop" ]; do echo "=== $(date +%s)"; jcmd "$DPID" VM.native_memory summary 2>&1 | grep -E 'Total:|^-  *(Other|Internal|Java Heap|Thread|Class) '; sleep 10; done ) > "$L/nmt.txt" & MPID=$!
log "samplers: jmx $SPID rss $RPID nmt $MPID"
sleep 6
echo "stress_start $(date +%s)" > "$L/markers.txt"
if [ "$MODE" = stall ]; then
  ( sleep 60; jcmd "$DPID" Thread.print > "$L/threaddump.txt" 2>&1 ) & TPID=$!
  log "+ timeout 180 tools/bin/cassandra-stress write duration=60s cl=ONE -col n=FIXED(5) size=FIXED(200) -rate threads=64 -schema replication(factor=1)"
  (cd "$C" && timeout -s KILL 180 tools/bin/cassandra-stress write duration=60s cl=ONE -col "n=FIXED(5)" "size=FIXED(200)" -rate threads=64 -schema "replication(factor=1)") > "$L/stress.log" 2>&1
  log "stress rc=$?"; wait "$TPID" 2>/dev/null; TPID=
  log "thread dump: $(grep -c 'MemtableAllocator\$SubAllocator.allocate' "$L/threaddump.txt" 2>/dev/null) frames in SubAllocator.allocate"
  DRAIN_LIMIT=60
else
  log "+ tools/bin/cassandra-stress write n=3000000 cl=ONE -col n=FIXED(5) size=FIXED(200) -rate threads=64 -schema replication(factor=1)"
  (cd "$C" && tools/bin/cassandra-stress write n=3000000 cl=ONE -col "n=FIXED(5)" "size=FIXED(200)" -rate threads=64 -schema "replication(factor=1)") > "$L/stress.log" 2>&1
  log "stress rc=$?"
fi
echo "stress_end $(date +%s)" >> "$L/markers.txt"
sleep 10
t0=$(date +%s); nt sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize" -mg -f Value > "$L/sjk-end.txt" 2>&1; log "sjk end took $(( $(date +%s) - t0 )) s: $(tail -1 "$L/sjk-end.txt")"
nt sjk mx -b "org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation" -mg -f Count > "$L/sjk-blocked-end.txt" 2>&1
touch "$L/stop"; sleep 3
tail -c +$((SL0+1)) "$N/logs/system.log" > "$L/system-after-start.log"
grep -E 'Flushing largest|Enqueuing flush' "$L/system-after-start.log" > "$L/flush-lines.txt"
grep -E '^(ERROR|WARN)' "$L/system-after-start.log" | head -200 > "$L/error-warn.txt"
exit 0
