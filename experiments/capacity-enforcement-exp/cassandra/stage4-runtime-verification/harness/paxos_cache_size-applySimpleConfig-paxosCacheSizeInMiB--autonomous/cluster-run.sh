#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-25) of paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous: one node lifetime.
# Adapted from harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/cluster-run.sh (knob, workload, phases,
# classes, read-back, compaction wait).
# usage: cluster-run.sh <label> <value: 2MiB | 32MiB | auto | ...>
#   start node (MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M), read back system_views.settings, sampler (JMX, every 2 s), baseline histogram,
#   schema, B3h control (NC LWTs on k = 1,000,000..), histogram, main (NW LWTs on k = 0..NW-1, three under-load histograms started
#   by the client), flush, wait for compactions, final histogram, stop, wipe.
# Env: C (clone, default $W/cassandra-run13), OUT (log root), NW (200000), NC (300).
# Node data under $W/node-pcs (wiped before and after). One node, 127.0.0.1. Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
LABEL=$1; VAL=$2
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run13}; N=$W/node-pcs
OUT=${OUT:-$W/logs/paxos_cache_size-applySimpleConfig/cluster}; NW=${NW:-200000}; NC=${NC:-300}
L=$OUT/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
FREE_G=$(df -g "$W" | tail -1 | awk '{print $4}')
note "run $LABEL paxos_cache_size=$VAL NW=$NW NC=$NC clone=$(git -C "$C" rev-parse HEAD) free_GiB=$FREE_G $(date +%s)"
[ "$FREE_G" -ge 20 ] || { log "ABORT: less than 20 GiB free"; exit 1; }
mkdir -p "$W/harness-bin-pcs"; javac -d "$W/harness-bin-pcs" "$H/PaxosSampler.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac PaxosSampler"; exit 1; }
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(paxos_cache_size|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
  | grep -v -E '^    - /var/lib/cassandra/data$' > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  if [ "$VAL" != auto ]; then echo "paxos_cache_size: $VAL"; fi; } >> "$Y"
tail -9 "$Y" > "$L/yaml-overrides.txt"
diff "$C/conf/cassandra.yaml" "$Y" > "$L/yaml-diff.txt"
grep -n -E '^paxos_variant|^paxos_state_purging|^memtable_allocation_type' "$Y" >> "$L/yaml-overrides.txt"
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
SPID=""
stop_node() {
  log "stopping node"
  touch "$L/stop"; [ -n "$SPID" ] && { for i in $(seq 1 10); do kill -0 "$SPID" 2>/dev/null || break; sleep 1; done; kill "$SPID" 2>/dev/null; }
  if kill -0 "$NPID" 2>/dev/null; then
    ( cd "$C" && bin/nodetool drain ) >> "$L/commands.log" 2>&1 & DRP=$!
    for i in $(seq 1 120); do kill -0 "$DRP" 2>/dev/null || break; sleep 1; done; kill "$DRP" 2>/dev/null; log "drain done or bounded"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill -9 "$NPID" 2>/dev/null
  fi
  pkill -9 -f 'org.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  pkill -f 'pcs-client.py' 2>/dev/null
  sleep 2; if pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"
  du -sh "$N/data" "$N/commitlog" >> "$L/commands.log" 2>&1
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
client() { local tag=$1; shift; local s0=$(date +%s); log "+ pcs-client.py $*"
  python3 "$H/pcs-client.py" "$@" > "$L/client-$tag.json" 2> "$L/client-$tag.err"; local rc=$?
  note "CLIENT $tag rc=$rc secs=$(( $(date +%s) - s0 )) $(cat "$L/client-$tag.json")"; return $rc; }
# shakedown fix H2: excerpt also lists Commit$Committed, PreHashedDecoratedKey, BTreeRow, BufferCell, LivenessInfo (full histograms unchanged)
CLS='Commit\$Committed|db\.PreHashedDecoratedKey|rows\.BTreeRow|rows\.BufferCell|db\.LivenessInfo|PaxosState\$Snapshot|PaxosState\$UnsafeSnapshot|PaxosState\$Key|service\.paxos\.PaxosState|Commit\$CommittedWithTTL|Commit\$AcceptedWithTTL|partitions\.PartitionUpdate|partitions\.BTreePartitionData|service\.paxos\.Ballot|rows\.EncodingStats|db\.MutableDeletionInfo|db\.BufferDecoratedKey|Murmur3Partitioner\$LongToken|caffeine\.cache\.PSMW|java\.util\.concurrent\.ConcurrentHashMap\$Node|\[Ljava\.util\.concurrent\.ConcurrentHashMap\$Node;| \[J| \[B|java\.nio\.HeapByteBuffer'
histo() { jmap -histo:live "$DPID" > "$L/histo-$1.txt" 2>&1; jcmd "$DPID" GC.heap_info > "$L/heapinfo-$1.txt" 2>&1; excerpt "$1"; }
excerpt() { # JDK 11 histograms may append the module, e.g. "[J (java.base@11.0.32.1)"
  grep -E "($CLS)( \(|\$)|^Total" "$L/histo-$1.txt" > "$L/histo-excerpt-$1.txt"
  local tot sn ps; tot=$(grep -E '^Total' "$L/histo-$1.txt" | tr -s ' '); sn=$(grep -E ' org\.apache\.cassandra\.service\.paxos\.PaxosState\$Snapshot$' "$L/histo-$1.txt" | tr -s ' ')
  ps=$(grep -E ' org\.apache\.cassandra\.service\.paxos\.PaxosState$' "$L/histo-$1.txt" | tr -s ' ')
  note "HISTO $1 total:$tot | Snapshot:${sn:- none} | PaxosState(ACTIVE):${ps:- none}"; }
phase() { echo "$1" > "$L/phase"; log "phase $1"; }
ntool() { (cd "$C" && bin/nodetool "$@") >> "$L/commands.log" 2>&1; log "nodetool $* rc=$?"; }
phase baseline
java -cp "$W/harness-bin-pcs" PaxosSampler 7199 "$L/samples.csv" "$L/phase" "$L/stop" ks t > "$L/sampler.err" 2>&1 & SPID=$!
client settings settings || exit 1
cp "$L/client-settings.json" "$L/readback-settings.json"
sleep 4
note "HEAP_COMMITTED_AT_START $(sed -n 2p "$L/samples.csv" | cut -d, -f4)"
histo 0-baseline
client schema schema || exit 1
phase control
client control lwt 1000000 $((1000000 + NC)) || exit 1
phase control-done; sleep 4
histo 1-control
phase main
client main lwt 0 "$NW" "$DPID" "$L"
for p in 25 50 75; do [ -f "$L/histo-load-$p.txt" ] && excerpt "load-$p"; done
phase main-done; sleep 4
ntool flush
phase flushed
for i in $(seq 1 150); do
  cs=$(cd "$C" && bin/nodetool compactionstats 2>/dev/null)
  # shakedown fix H1: 5.0.9 prints "pending tasks                    0" (no colon)
  if echo "$cs" | grep -Eq '^pending tasks:?[[:space:]]+0[[:space:]]*$' && ! echo "$cs" | grep -Eq '^[[:space:]]*[0-9a-f]{8}-[0-9a-f]{4}-'; then break; fi
  sleep 2
done
echo "$cs" > "$L/compactionstats-final.txt"; log "compactions settled after $((i*2)) s"
phase compacted; sleep 6
histo 2-end
( cd "$C" && bin/nodetool tablestats ks.t system.paxos ) > "$L/tablestats-final.txt" 2>&1
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -50 > "$L/error-warn.txt"
note "ERROR/WARN lines: $(wc -l < "$L/error-warn.txt" | tr -d ' '); OOM: $(grep -c "java.lang.OutOfMemoryError" "$N/logs/system.log")"
trap - EXIT; stop_node; finish
