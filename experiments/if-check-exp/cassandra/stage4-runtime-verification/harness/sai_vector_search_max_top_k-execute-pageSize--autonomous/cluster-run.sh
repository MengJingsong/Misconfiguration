#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of sai_vector_search_max_top_k-execute-pageSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   run 1: no variables (ROWS=20000, VS="1000 5000 10000", REPS=3)
#   shakedown only: ROWS=6000 VS="1000 5000" REPS=1 OUT=... cluster-run.sh
# One node, own conf under $W/node-topk (range/read timeouts 60 s, native_transport_timeout 60s), heap 2G, G1; the knob as
# -Dcassandra.sai.vector_search.max_top_k=<V> in the node's jvm-server.options. V=1000 start, setup, load, flush, count, restart;
# (load concurrency $LOADCONC, default 8); then per V: restart with V, read back V, wait 30 s, JMX heap poller every 100 ms, for each L of amended B3c, REPS times:
#   explicit GC over JMX; 2 s; probe.py q L; 3 s; the query's system.log slice.
# Env: C (clone, default $W/cassandra-run34), OUT (log dir), HB (compiled TkJmx dir).
set -uo pipefail
ROWS=${ROWS:-20000}; VS=${VS:-"1000 5000 10000"}; REPS=${REPS:-3}
# load concurrency 8 (amended B3c): JVector's builder pool allows availableProcessors()+1 = 11 concurrent memtable graph inserts here
LOADCONC=${LOADCONC:-8}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run34}; N=$W/node-topk; HB=${HB:-$W/harness-bin-topk}
OUT=${OUT:-$W/logs/sai_vector_search_max_top_k-execute-pageSize--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
nowms() { python3 -c 'import time; print(int(time.time()*1000))'; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN ROWS=$ROWS VS=[$VS] REPS=$REPS clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') start_epoch=$(date +%s)"
mkdir -p "$HB"; javac -d "$HB" "$H/TkJmx.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac TkJmx"; exit 1; }
JX() { java -cp "$HB" TkJmx "$@" 2>>"$L/jmx.err" | grep '^RESULT' || echo "RESULT jmx-failed"; }
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
cp "$N/conf/jvm-server.options" "$N/jvm-server.options.orig"
Y=$N/conf/cassandra.yaml
grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|read_request_timeout|range_request_timeout|native_transport_timeout):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides (sai_vector_search_max_top_k)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
  echo "read_request_timeout: 60000ms"; echo "range_request_timeout: 60000ms"; echo "native_transport_timeout: 60s"; } >> "$Y"
tail -13 "$Y" > "$L/yaml-overrides.txt"
diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff.txt"
setv() { # $1 V: the node's jvm-server.options = original + gc log + the knob
  cp "$N/jvm-server.options.orig" "$N/conf/jvm-server.options"
  { echo "-Xlog:gc*:file=$N/gc.log:time,uptime"; echo "-Dcassandra.sai.vector_search.max_top_k=$1"; } >> "$N/conf/jvm-server.options"
  tail -2 "$N/conf/jvm-server.options" > "$L/jvm-server-options-added-V$1.txt"; }
NT() { (cd "$C" && bin/nodetool "$@"); }
NPID=; PPID_POLL=
stop_poller() { [ -n "$PPID_POLL" ] || return; touch "$L/poll.stop"; sleep 1; kill "$PPID_POLL" 2>/dev/null; PPID_POLL=; log "heap poller stopped"; }
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
  for g in "$N"/gc.log*; do [ -f "$g" ] && cp "$g" "$L/"; done
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_poller; stop_node; finish' EXIT
start_node() { # $1 label $2 V
  local off=0; [ -f "$N/logs/system.log" ] && off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  setv "$2"
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f   ($1, V=$2)"
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) >> "$L/node.out" 2>&1 < /dev/null &
  NPID=$!; log "node launcher pid $NPID"
  local ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
    if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
  local dp; dp=$(pgrep -f "$DPAT" | head -1)
  log "node UN, statusbinary running; daemon pid $dp"
  local sl; sl=$(tail -c +$((off + 1)) "$N/logs/system.log")
  note "READBACK $1 V=$2 | ps_args_max_top_k=$(ps -o args= -p "$dp" | grep -o -- '-Dcassandra.sai.vector_search.max_top_k=[0-9]*' | tr '\n' ' ') | syslog_jvmargs_max_top_k=$(echo "$sl" | grep -m1 -o 'JVM Arguments: .*' | grep -o -- '-Dcassandra.sai.vector_search.max_top_k=[0-9]*' | tr '\n' ' ') | jmx_$(JX sysprop | sed 's/^RESULT sysprop //') | $(echo "$sl" | grep -m1 'range_request_timeout=' | grep -o -E '(range_request_timeout|read_request_timeout|native_transport_timeout|read_thresholds_enabled)=[^;,]*' | tr '\n' ' ')"
  note "JVMARGS $1 | $(echo "$sl" | grep -m1 -o 'JVM Arguments: .*' | grep -o -E -- '-Xm[sxn][0-9]*[GM]|-XX:\+UseG1GC|-XX:G1HeapRegionSize=[0-9a-z]*|-Xlog:gc\*:file=[^ ,]*' | tr '\n' ' ')"; }
PY() { python3 -I "$H/probe.py" "$@" 2>>"$L/client.err" | grep '^RESULT' || echo "RESULT missing (see client.err)"; }
stats() { NT tablestats v.vt 2>&1 | grep -E 'SSTable count:|Space used \(live\):|Memtable data size:|Local read count:' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }

# ---- 1. start (V=1000), setup, load, flush, count ----
FIRSTV=${VS%% *}
start_node "first-start" "$FIRSTV"
note "SETUP | $(PY setup)"
note "LOAD concurrency=$LOADCONC | $(PY load "$ROWS" "$LOADCONC")"
log "+ nodetool flush v vt"; NT flush v vt >> "$L/commands.log" 2>&1; note "FLUSH-RC $?"
sleep 5
note "COMPACTIONSTATS after-flush | $(NT compactionstats 2>&1 | tr '\n' ' ' | cut -c1-300)"
note "STATS after-load-flush | $(stats)"
note "COUNT after-load | $(PY count)"
note "SAI-BUILD lines | $(grep -c -E 'Index build of .* complete|Completed flushing|SSTableIndexWriter' "$N/logs/system.log" | tr '\n' ' ') index_errors=$(grep '^ERROR' "$N/logs/system.log" | grep -ci 'index')"
stop_node
lset() { case "$1" in 1000) echo "1000 1001";; *) echo "1000 $1 $(( $1 + 1 ))";; esac; }
for V in $VS; do
  start_node "V$V" "$V"
  log "+ sleep 30"; sleep 30
  note "STATS V=$V before-queries | $(stats)"
  note "COMPACTIONSTATS V=$V | $(NT compactionstats 2>&1 | tr '\n' ' ' | cut -c1-200)"
  QOFF=$(wc -c < "$N/logs/system.log" | tr -d ' '); note "QUERY-PHASE V=$V syslog_offset=$QOFF start_ms=$(nowms)"
  rm -f "$L/poll.stop"
  java -cp "$HB" TkJmx poll "$L/heap-V$V.tsv" "$L/poll.stop" 100 >> "$L/commands.log" 2>&1 &
  PPID_POLL=$!; log "heap poller pid $PPID_POLL (100 ms)"; sleep 3
  for LL in $(lset "$V"); do
    for r in $(seq 1 "$REPS"); do
      tag="V$V-L$LL-r$r"
      off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
      gcr=$(JX gc); m0=$(nowms); sleep 2; m1=$(nowms)
      log "+ probe.py q $LL   ($tag)"
      res=$(PY q "$LL"); m2=$(nowms); sleep 3; m3=$(nowms)
      tail -c +$((off + 1)) "$N/logs/system.log" > "$L/syslog-$tag.txt"
      note "QUERY $tag | pre_ms=$m0 probe_start_ms=$m1 probe_end_ms=$m2 post_end_ms=$m3 | $res | pre_gc_$(echo "$gcr" | grep -o 'heap_used=[0-9]*') | syslog error=$(grep -c '^ERROR' "$L/syslog-$tag.txt") warn=$(grep -c '^WARN' "$L/syslog-$tag.txt") compaction=$(grep -c 'Compacting\|Compacted' "$L/syslog-$tag.txt") oom=$(grep -cF 'java.lang.OutOfMemoryError' "$L/syslog-$tag.txt")"
    done
  done
  note "QUERY-PHASE-END V=$V end_ms=$(nowms)"
  stop_poller
  stop_node
done
note "ERRORS whole log: ERROR=$(grep -c '^ERROR' "$N/logs/system.log") OOM=$(cat "$N/logs/system.log" "$L/node.out" | grep -cF java.lang.OutOfMemoryError)"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -80 > "$L/error-warn.txt"
trap - EXIT; finish
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ')"
