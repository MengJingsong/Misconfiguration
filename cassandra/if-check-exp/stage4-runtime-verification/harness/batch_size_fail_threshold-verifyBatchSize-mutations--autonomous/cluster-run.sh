#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh [N]     run 1: no argument (N = 200); shakedown: e.g. 10
#   for F in 50 100 200 KiB: yaml (warn 5KiB, fail F), start, read back F from the startup config line, schema (IF NOT EXISTS),
#   runs multi 30, multi 10, single 30, multi 60; each: tablestats before, batch.py run, tablestats after (before flush),
#   nodetool flush b t, bytes (skipping snapshots/backups), count(*), the run's system.log lines, TRUNCATE; stop the node.
#   The data directory is kept across the three restarts (as filed); wiped before and after the tier.
# Env: C (clone, default $W/cassandra-run32), OUT (log dir).
set -uo pipefail
N_B=${1:-200}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run32}; N=$W/node-bsf
OUT=${OUT:-$W/logs/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN N=$N_B clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') start_epoch=$(date +%s)"
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
NT() { (cd "$C" && bin/nodetool "$@"); }
NPID=
stop_node() {
  [ -z "$NPID" ] && return
  log "stopping node (launcher pid $NPID)"
  if kill -0 "$NPID" 2>/dev/null; then
    NT stopdaemon >> "$L/commands.log" 2>&1 & SDP=$!
    for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill "$SDP" 2>/dev/null
    if kill -0 "$NPID" 2>/dev/null; then log "still alive after 60 s: kill"; kill "$NPID"; sleep 10; kill -9 "$NPID" 2>/dev/null; fi
  fi
  sleep 2; local left; left=$(pgrep -f "$DPAT")
  if [ -n "$left" ]; then log "WARNING: daemon still running ($left): kill -9"; kill -9 $left; sleep 2; fi
  pgrep -f "$DPAT" >/dev/null && log "WARNING: daemon still running" || log "no Cassandra daemon left"
  NPID=; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT
start_node() { # $1 F
  local F=$1
  grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|batch_size_warn_threshold|batch_size_fail_threshold):' "$C/conf/cassandra.yaml" > "$Y"
  { echo; echo "# stage-4 overrides (batch_size_fail_threshold)"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "batch_size_warn_threshold: 5KiB"; echo "batch_size_fail_threshold: ${F}KiB"; } >> "$Y"
  tail -11 "$Y" > "$L/yaml-overrides-F$F.txt"
  diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff-F$F.txt"
  local off=0; [ -f "$N/logs/system.log" ] && off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f   (F=${F}KiB)"
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) >> "$L/node.out" 2>&1 < /dev/null &
  NPID=$!; log "node launcher pid $NPID"
  local ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
    if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
  log "node UN, statusbinary running; daemon pid $(pgrep -f "$DPAT" | head -1)"
  local cfg; cfg=$(tail -c +$((off + 1)) "$N/logs/system.log" | grep -m1 'batch_size_fail_threshold=' | grep -o -E 'batch_size_(warn|fail)_threshold=[^;,]*' | tr '\n' ' ')
  note "READBACK F=$F | $cfg"
  note "JVMARGS F=$F | $(tail -c +$((off + 1)) "$N/logs/system.log" | grep -m1 -o 'JVM Arguments: .*' | grep -o -- '-Xm[sxn][0-9]*[GM]' | tr '\n' ' ')"; }
client() { echo "[$(date '+%F %T')] + batch.py $*" >> "$L/commands.log"; local r; r=$(python3 -I "$H/batch.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); echo "${r:-RESULT missing (see client.err)}"; }
stats() { NT tablestats b.t 2>&1 | grep -E 'Memtable data size:|Local write count:|SSTable count:' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }
tdir() { ls -d "$N/data/b/t-"* 2>/dev/null | head -1; }
onerun() { # $1 F $2 shape $3 B
  local F=$1 sh=$2 B=$3 tag="F$1-$2-$3" off
  off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  note "STATS $tag before | $(stats)"
  note "BYTES $tag before | $(python3 -I "$H/batch.py" bytes "$(tdir)" | grep '^RESULT')"
  note "CLIENT $tag | $(client run "$sh" "$B" "$N_B")"
  note "STATS $tag after-before-flush | $(stats)"
  log "+ nodetool flush b t"; NT flush b t >> "$L/commands.log" 2>&1; note "FLUSH-RC $tag $?"
  note "STATS $tag after-flush | $(stats)"
  note "BYTES $tag after | $(python3 -I "$H/batch.py" bytes "$(tdir)" | grep '^RESULT')"
  note "COUNT $tag | $(client count)"
  tail -c +$((off + 1)) "$N/logs/system.log" > "$L/syslog-$tag.txt"
  note "LOGLINES $tag | fail_error=$(grep '^ERROR' "$L/syslog-$tag.txt" | grep -c 'see batch_size_fail_threshold') any_fail_ref=$(grep -c 'see batch_size_fail_threshold' "$L/syslog-$tag.txt") warn_batch=$(grep '^WARN' "$L/syslog-$tag.txt" | grep -c 'Batch for \[b.t\] is of size') flushing_largest=$(grep -c 'Flushing largest' "$L/syslog-$tag.txt") first_error: $(grep -m1 '^ERROR' "$L/syslog-$tag.txt" | cut -c1-220)"
  note "TRUNCATE $tag | $(client truncate)"; }
for F in 50 100 200; do
  note "LIFETIME F=$F start_epoch=$(date +%s)"
  start_node "$F"
  note "SCHEMA F=$F | $(client schema)"
  onerun "$F" multi 30
  onerun "$F" multi 10
  onerun "$F" single 30
  onerun "$F" multi 60
  stop_node
  note "LIFETIME-END F=$F end_epoch=$(date +%s)"
done
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v -E 'see batch_size_fail_threshold|Batch for \[b.t\]' | cut -c1-300 | head -60 > "$L/error-warn-other.txt"
note "OTHER ERROR/WARN lines: $(wc -l < "$L/error-warn-other.txt" | tr -d ' ')"
grep -E 'Flushing largest|Enqueuing flush of b\.t|Enqueuing flush of t' "$N/logs/system.log" | cut -c1-250 > "$L/flush-lines.txt"
note "FLUSH-LOG-LINES: $(wc -l < "$L/flush-lines.txt" | tr -d ' '); automatic (Flushing largest): $(grep -c 'Flushing largest' "$L/flush-lines.txt")"
trap - EXIT; finish
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ')"
