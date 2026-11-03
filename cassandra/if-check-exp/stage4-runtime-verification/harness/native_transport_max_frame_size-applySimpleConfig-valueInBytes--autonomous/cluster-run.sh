#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-24) of native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous: one node start.
# usage: cluster-run.sh <outdir-name> <label> <knob: unset | 2MiB | 8MiB | 2048MiB>
#   unset/2MiB/8MiB: B3c phases (1)-(5) with metric reads between them, NMT every 1 s around the floods (B3d), drain, stop, wipe.
#   2048MiB: startup only, bounded to 120 s; "fails" = process exits + the B2f message + no "Startup complete" (B3e).
# Needs: source ~/Library/Caches/stage4/env.sh. Node from clone $C (default $W/cassandra-run5), data under $W/node-ntmfs (wiped before
# and after), logs under $W/logs/native_transport_max_frame_size-applySimpleConfig/<outdir-name>/<label>/. One node, 127.0.0.1.
set -uo pipefail
OUT=$1; LABEL=$2; KNOB=$3
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run5}; N=$W/node-ntmfs
L=$W/logs/native_transport_max_frame_size-applySimpleConfig/$OUT/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
nt() { (cd "$C" && timeout 60 bin/nodetool "$@"); }
cli() { python3 -I "$H/frame-client.py" "$@"; }
case $KNOB in unset) K=16777216;; 2MiB) K=2097152;; 8MiB) K=8388608;; 2048MiB) K=0;; *) echo "bad knob"; exit 2;; esac
ps -eo command | grep -q '[C]assandraDaemon' && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
log "run $LABEL knob=$KNOB K=$K clone=$(git -C "$C" rev-parse HEAD) harness=$(shasum -a 256 "$H/cluster-run.sh" "$H/frame-client.py" | awk '{print substr($1,1,12)}' | tr '\n' ' ')"
df -h "$W" | tail -1 >> "$L/commands.log"
# node directories and configuration (B3a amended)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(native_transport_max_frame_size|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  [ "$KNOB" = unset ] || echo "native_transport_max_frame_size: $KNOB"; } >> "$Y"
tail -10 "$Y" > "$L/yaml-overrides.txt"
echo "-XX:NativeMemoryTracking=summary" >> "$N/conf/jvm-server.options"
grep -n 'NativeMemoryTracking\|PerfDisableSharedMem\|maxOrder' "$N/conf/jvm-server.options" "$N/conf/jvm11-server.options" >> "$L/yaml-overrides.txt"
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
T0=$(date +%s)
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
MPID=
dpid() { pgrep -f 'org.apache.cassandra.service.CassandraDaemon' | head -1; }
stop_node() {
  log "stopping node"; touch "$L/stop"; [ -n "$MPID" ] && kill "$MPID" 2>/dev/null
  pkill -f "frame-client.py" 2>/dev/null
  if kill -0 "$NPID" 2>/dev/null; then
    nt drain >> "$L/commands.log" 2>&1; log "drain rc=$?"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
  fi
  D=$(dpid); [ -n "$D" ] && { log "kill -9 daemon $D"; kill -9 "$D"; }
  kill -9 "$NPID" 2>/dev/null
  sleep 2; if ps -eo command | grep -q '[C]assandraDaemon'; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi
  if pgrep -f frame-client.py >/dev/null; then log "WARNING: frame-client still running"; else log "no frame-client left"; fi; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"; cp "$N/logs/gc.log"* "$L/" 2>/dev/null
  du -sh "$N/data" "$N/commitlog" >> "$L/commands.log" 2>&1
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT

if [ "$KNOB" = 2048MiB ]; then
  while [ $(( $(date +%s) - T0 )) -lt 120 ]; do
    kill -0 "$NPID" 2>/dev/null || break
    if nt status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then break; fi
    sleep 2
  done
  if kill -0 "$NPID" 2>/dev/null; then alive=1; else alive=0; fi
  wait "$NPID" 2>/dev/null; rc=$?
  { echo "process_alive_at_end=$alive after $(( $(date +%s) - T0 )) s (exit status if exited: $rc)"
    echo "message_lines=$(grep -h -c 'native_transport_max_frame_size must be positive value' "$L/node.out" "$N/logs/system.log" 2>/dev/null | paste -sd+ - | bc)"
    echo "startup_complete_lines=$(grep -h -c 'Startup complete' "$L/node.out" "$N/logs/system.log" 2>/dev/null | paste -sd+ - | bc)"
    grep -h -m2 'native_transport_max_frame_size must be positive value' "$L/node.out" "$N/logs/system.log" 2>/dev/null; } > "$L/startup.txt"
  log "$(head -3 "$L/startup.txt" | tr '\n' ' ')"
  exit 0
fi

ok=0
while [ $(( $(date +%s) - T0 )) -lt 360 ]; do
  kill -0 "$NPID" 2>/dev/null || { log "node died during start"; break; }
  if nt status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(nt statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
echo "startup_complete=$ok after $(( $(date +%s) - T0 )) s" > "$L/startup.txt"; log "$(cat "$L/startup.txt")"
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DPID=$(dpid); log "daemon pid ${DPID:-none}"
SL0=$(wc -c < "$N/logs/system.log")
metrics() {  # one line per read: tag epoch Max Count BytesReceived
  local m c b
  m=$(nt sjk mx -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesReceivedPerRequest" -mg -f Max 2>&1 | tail -1)
  c=$(nt sjk mx -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesReceivedPerRequest" -mg -f Count 2>&1 | tail -1)
  b=$(nt sjk mx -b "org.apache.cassandra.metrics:type=ClientMessageSize,name=BytesReceived" -mg -f Count 2>&1 | tail -1)
  echo "METRIC $1 $(date +%s) max=$m count=$c bytesReceived=$b" | tee -a "$L/metrics.txt" >> "$L/commands.log"; }
log "+ frame-client schema"; cli schema >> "$L/client.jsonl" 2>> "$L/client.err"; log "rc=$?"
log "+ frame-client readback"; cli readback | tee -a "$L/readback.txt" >> "$L/client.jsonl" 2>> "$L/client.err"; log "readback $(cat "$L/readback.txt")"
metrics after-schema
k0=0
for f in 0.5 0.9 1.1 3; do
  log "+ frame-client single $K $f 20 $k0 4"; cli single "$K" "$f" 20 "$k0" 4 >> "$L/client.jsonl" 2>> "$L/client.err"; log "rc=$?"
  metrics "after-v4-$f"; k0=$((k0 + 20))
done
# NMT sampler (B3d amended): every 1 s from 10 s before the first flood to 10 s after the second
( while [ ! -e "$L/stop-nmt" ]; do echo "=== $(date +%s)"; jcmd "$DPID" VM.native_memory summary 2>&1 | grep -E 'Total:|^-  *(Other|Internal|Java Heap|Thread) ' -A1 | grep -v -- '^--$'; sleep 1; done ) > "$L/nmt.txt" & MPID=$!
sleep 10
echo "flood_rejected_start $(date +%s)" >> "$L/markers.txt"; log "+ frame-client flood $K 3 60 8"
cli flood "$K" 3 60 8 > "$L/flood-rejected.jsonl" 2>> "$L/client.err"; log "rc=$?"
echo "flood_rejected_end $(date +%s)" >> "$L/markers.txt"
metrics after-flood-rejected
sleep 20
echo "flood_accepted_start $(date +%s)" >> "$L/markers.txt"; log "+ frame-client flood $K 0.9 60 8"
cli flood "$K" 0.9 60 8 > "$L/flood-accepted.jsonl" 2>> "$L/client.err"; log "rc=$?"
echo "flood_accepted_end $(date +%s)" >> "$L/markers.txt"
sleep 10; touch "$L/stop-nmt"; sleep 2; kill "$MPID" 2>/dev/null; MPID=
metrics after-flood-accepted
log "+ frame-client single $K 1.1 20 $k0 5"; cli single "$K" 1.1 20 "$k0" 5 >> "$L/client.jsonl" 2>> "$L/client.err"; log "rc=$?"
metrics after-v5-1.1
tail -c +$((SL0+1)) "$N/logs/system.log" > "$L/system-after-start.log"
grep -E '^(ERROR|WARN)' "$L/system-after-start.log" | head -200 > "$L/error-warn.txt"
exit 0
