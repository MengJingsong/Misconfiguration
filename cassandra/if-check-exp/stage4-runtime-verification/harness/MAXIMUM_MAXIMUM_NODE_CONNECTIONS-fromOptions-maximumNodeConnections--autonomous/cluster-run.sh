#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   run 1: no variables (ROWS=20000).  shakedown: ROWS=2000 OUT=<dir> cluster-run.sh
# One node from the clone, own conf under $W/node-mnc, MAX_HEAP_SIZE=2G, memtable_heap_space 1024MiB,
# -Dcassandra.sai.vector.allow_custom_parameters=true in the node's jvm-server.options.
# Steps: start; setup (tables t_16, t_128, t_512, t_16b400, t_513 and their indexes; idx_513 expected rejected);
# per loaded table (t_16, t_128, t_512, t_16b400): class histogram, load ROWS (concurrency 8), class histogram, count,
# tablestats, nodetool flush k <t>, file sizes; then nodetool compact k, wait for no pending/active compaction, file sizes; stop.
# Env: C (clone, default $W/cassandra-run39), OUT (log dir).
set -uo pipefail
ROWS=${ROWS:-20000}; LOADCONC=${LOADCONC:-8}
TABLES="t_16 t_128 t_512 t_16b400"
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run39}; N=$W/node-mnc
OUT=${OUT:-$W/logs/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN ROWS=$ROWS LOADCONC=$LOADCONC clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') start_epoch=$(date +%s)"
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|memtable_heap_space):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides (MAXIMUM_MAXIMUM_NODE_CONNECTIONS)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
  echo "memtable_heap_space: 1024MiB"; } >> "$Y"
tail -11 "$Y" > "$L/yaml-overrides.txt"
diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff.txt"
{ echo "-Xlog:gc*:file=$N/gc.log:time,uptime"; echo "-Dcassandra.sai.vector.allow_custom_parameters=true"; } >> "$N/conf/jvm-server.options"
tail -2 "$N/conf/jvm-server.options" > "$L/jvm-server-options-added.txt"
NT() { (cd "$C" && bin/nodetool "$@"); }
NPID=; DP=
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
  [ -f "$N/logs/debug.log" ] && grep -E 'Writing graph|Skipping PQ|Computing PQ|Flushed to|Compacted' "$N/logs/debug.log" | cut -c1-400 > "$L/debug-graph-lines.txt"
  for g in "$N"/gc.log*; do [ -f "$g" ] && cp "$g" "$L/"; done
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) >> "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DP=$(pgrep -f "$DPAT" | head -1); log "node UN, statusbinary running; daemon pid $DP"
note "READBACK ps_allow_custom=$(ps -o args= -p "$DP" | grep -o -- '-Dcassandra.sai.vector.allow_custom_parameters=[a-z]*' | tr '\n' ' ') | syslog_jvmargs_allow_custom=$(grep -m1 -o 'JVM Arguments: .*' "$N/logs/system.log" | grep -o -- '-Dcassandra.sai.vector.allow_custom_parameters=[a-z]*' | tr '\n' ' ') | heap=$(grep -m1 -o 'JVM Arguments: .*' "$N/logs/system.log" | grep -o -E -- '-Xm[sx][0-9]*[GM]|-XX:\+UseG1GC' | tr '\n' ' ') | memtable_heap_space=$(grep -m1 -o 'memtable_heap_space=[^;,]*' "$N/logs/system.log")"
PY() { python3 -I "$H/probe.py" "$@" 2>>"$L/client.err" | grep '^RESULT' || echo "RESULT missing (see client.err)"; }
HISTO() { # $1 tag -> histogram file and one summary field set
  jcmd "$DP" GC.class_histogram > "$L/histo-$1.txt" 2>&1
  awk '/^Total/ {t=$3} $4=="[I" {i=$3} $4=="[F" {f=$3} END {printf "live_total=%s int_arr=%s float_arr=%s", t, i, f}' "$L/histo-$1.txt"; }
stats() { NT tablestats "k.$1" 2>&1 | grep -E 'SSTable count:|Space used \(live\):|Memtable cell count:|Memtable data size:|Memtable off heap memory used:' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }

note "SETUP | $(PY setup)"
for T in $TABLES; do
  note "HISTO before-$T | $(HISTO before-$T)"
  log "+ probe.py load $T $ROWS $LOADCONC"
  note "LOAD $T | $(PY load "$T" "$ROWS" "$LOADCONC")"
  note "HISTO after-$T | $(HISTO after-$T)"
  note "COUNT $T | $(PY count "$T")"
  note "STATS before-flush $T | $(stats "$T")"
  log "+ nodetool flush k $T"; NT flush k "$T" >> "$L/commands.log" 2>&1; note "FLUSH-RC $T $?"
  sleep 3
  note "STATS after-flush $T | $(stats "$T")"
  note "$(python3 -I "$H/files.py" "$N/data/k" after-flush "$T")"
done
note "COMPACTIONSTATS before-compact | $(NT compactionstats 2>&1 | tr '\n' ' ' | cut -c1-300)"
log "+ nodetool compact k"; NT compact k >> "$L/commands.log" 2>&1; note "COMPACT-RC $?"
for i in $(seq 1 60); do
  # 5.0 prints 'pending tasks   0' (no colon) and one row per active task with keyspace and table columns (fixed after shakedown 1)
  cs=$(NT compactionstats 2>&1); echo "$cs" | grep -q -E 'pending tasks[[:space:]]*:?[[:space:]]*0([[:space:]]|$)' && ! echo "$cs" | grep -q -E '[[:space:]]k[[:space:]]+t_' && { log "compactions done after $i polls"; break; }; sleep 2
done
sleep 10
note "COMPACTIONSTATS after-compact | $(NT compactionstats 2>&1 | tr '\n' ' ' | cut -c1-300)"
for T in $TABLES; do
  note "STATS after-compact $T | $(stats "$T")"
  note "$(python3 -I "$H/files.py" "$N/data/k" after-compact "$T")"
done
note "SAI lines | $(grep -c -E 'Compacting|Compacted' "$N/logs/system.log") compaction lines; index_errors=$(grep '^ERROR' "$N/logs/system.log" | grep -ci 'index')"
note "ERRORS whole log: ERROR=$(grep -c '^ERROR' "$N/logs/system.log") OOM=$(cat "$N/logs/system.log" "$L/node.out" | grep -cF java.lang.OutOfMemoryError)"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -80 > "$L/error-warn.txt"
stop_node
trap - EXIT; finish
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ') clone_status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
