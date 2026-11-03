#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   run 1: no variables (NGROUPS=50 PER=2000 -> N=100,000 rows of 4 KiB; REPS=3)
#   shakedown only: NGROUPS=50 PER=400 REPS=1 OUT=... cluster-run.sh
# One node, own conf under $W/node-dps (read_request_timeout 60000ms, native_transport_timeout 60s), heap 2G, gc log,
# Byteman agent (rules.btm, observation only) on the node JVM only; setup and load, flush, restart, wait 30 s;
# JMX heap poller every 100 ms; Qg-off, Qg-1000, Qg-50000, Qa-off, REPS times each (Qa last: it may OOM the node):
#   explicit GC over JMX; coordinator/local read counts before; 2 s; probe.py q; 3 s; counts after; the query's node.out
#   (Byteman) and system.log slices.
# Env: C (clone, default $W/cassandra-run35), OUT (log dir), HB (compiled DpJmx dir).
set -uo pipefail
NGROUPS=${NGROUPS:-50}; PER=${PER:-2000}; REPS=${REPS:-3}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run35}; N=$W/node-dps; HB=${HB:-$W/harness-bin-dps}
OUT=${OUT:-$W/logs/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
BMJAR=$C/build/lib/jars/byteman-4.0.20.jar
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
nowms() { python3 -c 'import time; print(int(time.time()*1000))'; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
[ -f "$BMJAR" ] || { log "ABORT: no $BMJAR"; exit 1; }
note "RUN NGROUPS=$NGROUPS PER=$PER ROWS=$((NGROUPS * PER)) REPS=$REPS clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') rules_sha256=$(shasum -a 256 "$H/rules.btm" | cut -c1-16) start_epoch=$(date +%s)"
mkdir -p "$HB"; javac -d "$HB" "$H/DpJmx.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac DpJmx"; exit 1; }
JX() { java -cp "$HB" DpJmx "$@" 2>>"$L/jmx.err" | grep '^RESULT' || echo "RESULT jmx-failed"; }
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|read_request_timeout|native_transport_timeout):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides (SelectStatement.DEFAULT_PAGE_SIZE)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
  echo "read_request_timeout: 60000ms"; echo "native_transport_timeout: 60s"; } >> "$Y"
echo "-Xlog:gc*:file=$N/gc.log:time,uptime" >> "$N/conf/jvm-server.options"
tail -12 "$Y" > "$L/yaml-overrides.txt"; tail -1 "$N/conf/jvm-server.options" > "$L/jvm-server-options-added.txt"
diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff.txt"
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
  [ -f "$N/gc.log" ] && cp "$N/gc.log" "$L/gc.log"
  ls "$N/logs" > "$L/node-logs-listing.txt" 2>/dev/null
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_poller; stop_node; finish' EXIT
start_node() { # $1 label
  local off=0; [ -f "$N/logs/system.log" ] && off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs JVM_EXTRA_OPTS=-javaagent:$BMJAR=script:$H/rules.btm bin/cassandra -f   ($1)"
  ( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" JVM_EXTRA_OPTS="-javaagent:$BMJAR=script:$H/rules.btm" exec bin/cassandra -f ) >> "$L/node.out" 2>&1 < /dev/null &
  NPID=$!; log "node launcher pid $NPID"
  local ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
    if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
  log "node UN, statusbinary running; daemon pid $(pgrep -f "$DPAT" | head -1)"
  local sl; sl=$(tail -c +$((off + 1)) "$N/logs/system.log")
  note "READBACK $1 | $(echo "$sl" | grep -m1 'read_request_timeout=' | grep -o -E '(read_request_timeout|native_transport_timeout|read_thresholds_enabled|coordinator_read_size_fail_threshold|local_read_size_fail_threshold)=[^;,]*' | tr '\n' ' ')"
  note "JVMARGS $1 | $(echo "$sl" | grep -m1 -o 'JVM Arguments: .*' | grep -o -E -- '-Xm[sxn][0-9]*[GM]|-XX:\+UseG1GC|-XX:G1HeapRegionSize=[0-9a-z]*|-Xlog:gc\*:file=[^ ,]*|-javaagent:[^ ,]*' | tr '\n' ' ')"; }
PY() { python3 -I "$H/probe.py" "$@" 2>>"$L/client.err" | grep '^RESULT' || echo "RESULT missing (see client.err)"; }
stats() { NT tablestats g.t 2>&1 | grep -E 'SSTable count:|Space used \(live\):|Memtable data size:|Compacted partition maximum bytes:|Local read count:' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }

# ---- 1. start, setup, load, flush ----
start_node "first-start"
note "SETUP | $(PY setup)"
note "LOAD | $(PY load "$NGROUPS" "$PER" 32)"
log "+ nodetool flush g t"; NT flush g t >> "$L/commands.log" 2>&1; note "FLUSH-RC $?"
note "STATS after-load-flush | $(stats)"
note "COUNT after-load | $(PY count)"
# ---- restart for a fresh JVM, wait 30 s ----
stop_node
start_node "restart"
log "+ sleep 30"; sleep 30
note "STATS before-queries | $(stats)"
note "BM-RULES-LOADED | $(grep -c 'BM-' "$L/node.out") BM lines so far; agent errors: $(grep -v -E 'JVM Arguments|Node configuration|CompileCommand' "$L/node.out" | grep -c -E 'org\.jboss\.byteman|^Rule\.|ERROR : ')"
QOFF=$(wc -c < "$N/logs/system.log" | tr -d ' '); note "QUERY-PHASE syslog_offset=$QOFF start_ms=$(nowms)"
# ---- heap poller ----
rm -f "$L/poll.stop"
java -cp "$HB" DpJmx poll "$L/heap.tsv" "$L/poll.stop" 100 >> "$L/commands.log" 2>&1 &
PPID_POLL=$!; log "heap poller pid $PPID_POLL (100 ms)"; sleep 3
onequery() { # $1 qname $2 which $3 fetch $4 rep
  local tag="$1-r$4" off boff cb ca m0 m1 m2 m3 res gcr
  kill -0 "$NPID" 2>/dev/null || { note "QUERY $tag | SKIPPED node not running"; return; }
  off=$(wc -c < "$N/logs/system.log" | tr -d ' '); boff=$(wc -c < "$L/node.out" | tr -d ' ')
  gcr=$(JX gc); cb=$(JX counts); m0=$(nowms); sleep 2; m1=$(nowms)
  log "+ probe.py q $2 $3   ($tag)"
  res=$(PY q "$2" "$3"); m2=$(nowms); sleep 3; m3=$(nowms); ca=$(JX counts)
  tail -c +$((off + 1)) "$N/logs/system.log" > "$L/syslog-$tag.txt"
  tail -c +$((boff + 1)) "$L/node.out" | grep '^BM-' > "$L/bm-$tag.txt"
  note "QUERY $tag | pre_ms=$m0 probe_start_ms=$m1 probe_end_ms=$m2 post_end_ms=$m3 | $res | before $(echo "$cb" | sed 's/RESULT counts //') | after $(echo "$ca" | sed 's/RESULT counts //') | pre_gc_$(echo "$gcr" | grep -o 'heap_used=[0-9]*') | bm_resp=$(grep -c '^BM-RESP' "$L/bm-$tag.txt") bm_page=$(grep -c '^BM-PAGE' "$L/bm-$tag.txt") | syslog error=$(grep -c '^ERROR' "$L/syslog-$tag.txt") warn=$(grep -c '^WARN' "$L/syslog-$tag.txt") oom=$(grep -c -F 'java.lang.OutOfMemoryError' "$L/syslog-$tag.txt") compaction=$(grep -c 'Compacting\|Compacted' "$L/syslog-$tag.txt")"; }
for r in $(seq 1 "$REPS"); do onequery Qg-off qg off "$r"; done
for r in $(seq 1 "$REPS"); do onequery Qg-1000 qg 1000 "$r"; done
for r in $(seq 1 "$REPS"); do onequery Qg-50000 qg 50000 "$r"; done
for r in $(seq 1 "$REPS"); do onequery Qa-off qa off "$r"; done
note "QUERY-PHASE-END end_ms=$(nowms) node_alive=$(kill -0 "$NPID" 2>/dev/null && echo yes || echo no)"
stop_poller
kill -0 "$NPID" 2>/dev/null && note "STATS after-queries | $(stats)"
tail -c +$((QOFF + 1)) "$N/logs/system.log" > "$L/syslog-query-phase.txt"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | cut -c1-300 | head -80 > "$L/error-warn-all.txt"
note "ERROR/WARN lines (whole log): $(wc -l < "$L/error-warn-all.txt" | tr -d ' '); ERROR in query phase: $(grep -c '^ERROR' "$L/syslog-query-phase.txt"); java.lang.OutOfMemoryError: $(grep -c -F 'java.lang.OutOfMemoryError' "$N/logs/system.log" "$L/node.out" | tr '\n' ' ')"
stop_node
trap - EXIT; finish
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ') clone_status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
python3 -I "$H/summarize.py" "$L" > /dev/null 2>> "$L/commands.log"; log "readings.txt written ($(wc -l < "$L/readings.txt" | tr -d " ") lines)"
