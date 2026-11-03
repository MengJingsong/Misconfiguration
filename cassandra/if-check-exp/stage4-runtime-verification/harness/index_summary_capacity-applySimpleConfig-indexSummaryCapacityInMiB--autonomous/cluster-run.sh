#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-25) of index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous: one node lifetime.
# Adapted from harness/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous/cluster-run.sh (knob, interval,
# workload, phases, JMX sampler, R1 invoke, RSS) and the paxos harness's compaction wait (its fix H1: no colon after "pending tasks").
# usage: cluster-run.sh <label> <capacity: 2MiB | 8MiB | auto | ...> <interval: 1m | null>
#   start node (MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M), read back (log line + MBean), sampler (JMX, every 5 s) to the end,
#   stress write NW partitions (keysize 128), flush, compaction wait, no-read window (NOREAD s), stress read NR ops,
#   10 s, [null interval: PRE s], RSS x3, R1 (MBean redistributeSummaries), RSS x3, window (AFTER s; null interval: 60 s),
#   final IndexIntervals + tablestats, stop, wipe.
# Env: C (clone, default $W/cassandra-run14), OUT (log root), NW (15000000), NR (1000000), NOREAD (75), AFTER (150), PRE (150).
# Node data under $W/node-isc (wiped before and after). One node, 127.0.0.1. Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
LABEL=$1; VAL=$2; IVL=$3
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run14}; N=${W:?}/node-isc
OUT=${OUT:-$W/logs/index_summary_capacity-applySimpleConfig/cluster}; NW=${NW:-15000000}; NR=${NR:-1000000}
NOREAD=${NOREAD:-75}; AFTER=${AFTER:-150}; PRE=${PRE:-150}
L=${OUT:?}/${LABEL:?}; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "run $LABEL index_summary_capacity=$VAL index_summary_resize_interval=$IVL NW=$NW NR=$NR clone=$(git -C "$C" rev-parse HEAD) $(date +%s)"
DF=$(df -g "$W" | tail -1 | awk '{print $4}'); note "free disk GiB: $DF"; [ "$DF" -ge 20 ] || { log "ABORT: < 20 GiB free"; exit 1; }
mkdir -p "$W/harness-bin-isc"; javac -d "$W/harness-bin-isc" "$H/ISSampler.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac ISSampler"; exit 1; }
J() { java -cp "$W/harness-bin-isc" ISSampler "$@"; }
rm -rf "${N:?}"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(index_summary_capacity|index_summary_resize_interval|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" \
  | grep -v -E '^    - /var/lib/cassandra/data$' > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  if [ "$VAL" = auto ]; then echo "index_summary_capacity:"; else echo "index_summary_capacity: $VAL"; fi
  if [ "$IVL" = null ]; then echo "index_summary_resize_interval:"; else echo "index_summary_resize_interval: $IVL"; fi; } >> "$Y"
tail -10 "$Y" > "$L/yaml-overrides.txt"
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
    for i in $(seq 1 120); do kill -0 "$DRP" 2>/dev/null || break; sleep 1; done; kill "$DRP" 2>/dev/null; log "drain done or bounded"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill -9 "$NPID" 2>/dev/null
  fi
  pkill -9 -f 'org.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  pkill -9 -f 'org.apache.cassandra.stress.Stress' 2>/dev/null
  pkill -f 'ISSampler sample' 2>/dev/null
  sleep 2; if pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"
  du -sh "$N/data" "$N/commitlog" >> "$L/commands.log" 2>&1
  rm -rf "${N:?}"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DPID=$(pgrep -f org.apache.cassandra.service.CassandraDaemon | head -1); log "node UN, statusbinary running; daemon pid $DPID"
RB=$(grep -o 'Initializing index summary manager with a memory pool size of [-0-9]* MB and a resize interval of [-0-9]* minutes' "$N/logs/system.log" | head -1)
echo "$RB" > "$L/readback-line.txt"; note "READBACK $RB"
J attrs 7199 > "$L/readback-mbean.txt" 2>&1; note "READBACK-MBEAN $(cat "$L/readback-mbean.txt")"
case $VAL in auto) EXP=102;; *) EXP=${VAL%MiB};; esac
case $IVL in null) EXPI=-1;; *) EXPI=${IVL%m};; esac
[ "$RB" = "Initializing index summary manager with a memory pool size of $EXP MB and a resize interval of $EXPI minutes" ] \
  || { note "READBACK MISMATCH expected $EXP MB / $EXPI minutes"; exit 1; }
grep -q "capacity_mb=$EXP .*resize_min=$EXPI " "$L/readback-mbean.txt" || { note "READBACK-MBEAN MISMATCH"; exit 1; }
LOGOFF=$(wc -c < "$N/logs/system.log" | tr -d ' ')
stress() { local tag=$1; shift; local s0=$(date +%s); log "+ tools/bin/cassandra-stress $*"
  (cd "$C" && tools/bin/cassandra-stress "$@") > "$L/stress-$tag.log" 2>&1; local rc=$?
  sed -n '/^Results:/,$p' "$L/stress-$tag.log" | head -30 > "$L/stress-$tag-results.txt"
  note "STRESS $tag rc=$rc secs=$(( $(date +%s) - s0 )) $(grep -E '^Total partitions' "$L/stress-$tag.log" | tr -s ' ' | head -1) | $(grep -E '^Op rate' "$L/stress-$tag.log" | tr -s ' ' | head -1) | $(grep -E '^Total errors' "$L/stress-$tag.log" | tr -s ' ' | head -1)"; }
ntool() { (cd "$C" && bin/nodetool "$@") >> "$L/commands.log" 2>&1; log "nodetool $* rc=$?"; }
tstats() { (cd "$C" && bin/nodetool tablestats keyspace1.standard1) > "$L/tablestats-$1.txt" 2>&1
  note "TABLESTATS $1 $(grep -E 'SSTable count|Index summary off heap memory used|Number of partitions' "$L/tablestats-$1.txt" | tr -s ' ' | tr '\n' '|')"; }
rss() { local i; for i in 1 2 3; do note "RSS $1 $i $(python3 -c 'import time; print(int(time.time()*1000))') $(ps -o rss= -p "$DPID" | tr -d ' ') KiB"; sleep 2; done; }
phase() { echo "$1" > "$L/phase"; log "phase $1"; }
redist_lines() { tail -c +$((LOGOFF+1)) "$N/logs/system.log" | grep -E 'Redistributing index summaries|Beginning redistribution|index summaries: downsample|Completed resizing of index summaries' | cut -c1-260 > "$L/redistribution-lines.txt"
  note "REDIST-LINES $1 completed=$(grep -c 'Completed resizing' "$L/redistribution-lines.txt") started=$(grep -c 'Redistributing index summaries' "$L/redistribution-lines.txt")"; }
phase baseline
J sample 7199 "$L/samples.csv" "$L/phase" "$L/stop" > "$L/sampler.err" 2>&1 & SPID=$!
sleep 10
phase write
stress write write n=$NW keysize=128 no-warmup -pop seq=1..$NW -col 'n=FIXED(1)' 'size=FIXED(16)' -rate threads=100 -node 127.0.0.1
phase flush
ntool flush keyspace1
phase compact
for i in $(seq 1 600); do
  cs=$(cd "$C" && bin/nodetool compactionstats 2>/dev/null)
  if echo "$cs" | grep -Eq '^pending tasks:?[[:space:]]+0[[:space:]]*$' && ! echo "$cs" | grep -Eq '^[[:space:]]*[0-9a-f]{8}-[0-9a-f]{4}-'; then break; fi
  sleep 2
done
echo "$cs" > "$L/compactionstats-settled.txt"; note "COMPACTION settled after $((i*2)) s"
tstats settled
phase noread; sleep "$NOREAD"
redist_lines noread
tstats noread
phase read
stress read read n=$NR keysize=128 no-warmup -pop "dist=UNIFORM(1..$NW)" -col 'n=FIXED(1)' 'size=FIXED(16)' -rate threads=50 -node 127.0.0.1
phase readdone; sleep 10
if [ "$IVL" = null ]; then phase pre-r1; sleep "$PRE"; fi
tstats pre-r1
redist_lines pre-r1
phase rss-before; rss before
phase r1
J invoke 7199 > "$L/r1.txt" 2>&1; note "R1 $(grep -E '^(BEFORE|INVOKED|AFTER)' "$L/r1.txt" | tr '\n' '|')"
phase rss-after; rss after
tstats after-r1
phase after-r1
if [ "$IVL" = null ]; then sleep 60; else sleep "$AFTER"; fi
phase final
J intervals 7199 > "$L/intervals-final.txt" 2>&1; note "FINAL $(grep '^ATTRS' "$L/intervals-final.txt")"
tstats final
redist_lines final
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -50 > "$L/error-warn.txt"
note "ERROR/WARN lines: $(wc -l < "$L/error-warn.txt" | tr -d ' '); OOM: $(grep -c "java.lang.OutOfMemoryError" "$N/logs/system.log")"
trap - EXIT; stop_node; finish
