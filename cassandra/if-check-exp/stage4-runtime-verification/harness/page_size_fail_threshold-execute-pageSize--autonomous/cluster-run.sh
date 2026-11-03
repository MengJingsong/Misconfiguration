#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of page_size_fail_threshold-execute-pageSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh
#   run 1: no variables (ROWS=100000, BIG=50000, REPS=3, thresholds 500:1000 then 5000:10000 then -1:-1)
#   shakedown only: ROWS=20000 BIG=10000 REPS=1 OUT=... cluster-run.sh
# One node, own conf under $W/node-psf (PasswordAuthenticator, CassandraAuthorizer, page_size 500/1000 in the yaml,
# read_request_timeout 60000ms), heap 2G; setup and load as cassandra, flush, restart, wait 30 s; JMX heap poller every 100 ms;
# for each threshold pair (the first from the yaml, the next two set over JMX and read back): Q1..Q5, REPS times each, as `app`:
#   explicit GC over JMX; rowsread before; 2 s; probe.py q; 3 s; rowsread after; the query's system.log slice.
# Env: C (clone, default $W/cassandra-run33), OUT (log dir), HB (compiled PsJmx dir).
set -uo pipefail
ROWS=${ROWS:-100000}; BIG=${BIG:-50000}; REPS=${REPS:-3}; TPAIRS=${TPAIRS:-"500:1000 5000:10000 -1:-1"}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run33}; N=$W/node-psf; HB=${HB:-$W/harness-bin-psf}
OUT=${OUT:-$W/logs/page_size_fail_threshold-execute-pageSize--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
nowms() { python3 -c 'import time; print(int(time.time()*1000))'; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN ROWS=$ROWS BIG=$BIG REPS=$REPS TPAIRS=[$TPAIRS] clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') start_epoch=$(date +%s)"
mkdir -p "$HB"; javac -d "$HB" "$H/PsJmx.java" >> "$L/commands.log" 2>&1 || { log "ABORT: javac PsJmx"; exit 1; }
JX() { java -cp "$HB" PsJmx "$@" 2>>"$L/jmx.err" | grep '^RESULT' || echo "RESULT jmx-failed"; }
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|authenticator|authorizer|read_request_timeout|page_size_warn_threshold|page_size_fail_threshold):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides (page_size_fail_threshold)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
  echo "authenticator: PasswordAuthenticator"; echo "authorizer: CassandraAuthorizer"
  echo "read_request_timeout: 60000ms"
  echo "page_size_warn_threshold: 500"; echo "page_size_fail_threshold: 1000"; } >> "$Y"
echo "-Xlog:gc*:file=$N/gc.log:time,uptime" >> "$N/conf/jvm-server.options"
tail -14 "$Y" > "$L/yaml-overrides.txt"; tail -1 "$N/conf/jvm-server.options" > "$L/jvm-server-options-added.txt"
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
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_poller; stop_node; finish' EXIT
start_node() { # $1 label
  local off=0; [ -f "$N/logs/system.log" ] && off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f   ($1)"
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
  local sl; sl=$(tail -c +$((off + 1)) "$N/logs/system.log")
  note "READBACK $1 | $(echo "$sl" | grep -m1 'page_size_fail_threshold=' | grep -o -E '(page_size_(warn|fail)_threshold|authenticator|authorizer|read_request_timeout)=[^;,]*' | tr '\n' ' ')"
  note "JVMARGS $1 | $(echo "$sl" | grep -m1 -o 'JVM Arguments: .*' | grep -o -E -- '-Xm[sxn][0-9]*[GM]|-XX:\+UseG1GC|-XX:G1HeapRegionSize=[0-9a-z]*|-Xlog:gc\*:file=[^ ,]*' | tr '\n' ' ')"; }
PY() { python3 -I "$H/probe.py" "$@" 2>>"$L/client.err" | grep '^RESULT' || echo "RESULT missing (see client.err)"; }
stats() { NT tablestats p.wide 2>&1 | grep -E 'SSTable count:|Space used \(live\):|Memtable data size:|Compacted partition maximum bytes:|Local read count:' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }

# ---- 1. start, setup, load, flush ----
start_node "first-start"
note "SETUP | $(PY setup)"
note "LOAD | $(PY load "$ROWS" 32)"
log "+ nodetool flush p wide"; NT flush p wide >> "$L/commands.log" 2>&1; note "FLUSH-RC $?"
note "STATS after-load-flush | $(stats)"
note "COUNT after-load | $(PY count)"
# ---- restart for a fresh JVM, wait 30 s ----
stop_node
start_node "restart"
log "+ sleep 30"; sleep 30
note "STATS before-queries | $(stats)"
QOFF=$(wc -c < "$N/logs/system.log" | tr -d ' '); note "QUERY-PHASE syslog_offset=$QOFF start_ms=$(nowms)"
# ---- heap poller ----
rm -f "$L/poll.stop"
java -cp "$HB" PsJmx poll "$L/heap.tsv" "$L/poll.stop" 100 >> "$L/commands.log" 2>&1 &
PPID_POLL=$!; log "heap poller pid $PPID_POLL (100 ms)"; sleep 3
onequery() { # $1 thr-tag $2 qname $3 fetch $4 limit $5 rep
  local tag="T$1-$2-r$5" off rb ra m0 m1 m2 m3 res
  off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  gcr=$(JX gc); rb=$(JX rowsread); m0=$(nowms); sleep 2; m1=$(nowms)
  log "+ probe.py q $3 $4   ($tag)"
  res=$(PY q "$3" "$4"); m2=$(nowms); sleep 3; m3=$(nowms); ra=$(JX rowsread)
  tail -c +$((off + 1)) "$N/logs/system.log" > "$L/syslog-$tag.txt"
  note "QUERY $tag | pre_ms=$m0 probe_start_ms=$m1 probe_end_ms=$m2 post_end_ms=$m3 | $res | rowsread_before=$(echo "$rb" | grep -o 'count=[0-9]*') rowsread_after=$(echo "$ra" | grep -o 'count=[0-9]*') | pre_gc_$(echo "$gcr" | grep -o 'heap_used=[0-9]*') | syslog error_pagesize=$(grep '^ERROR' "$L/syslog-$tag.txt" | grep -c 'page_size violated') warn_pagesize=$(grep '^WARN' "$L/syslog-$tag.txt" | grep -c 'page_size violated') other_error=$(grep '^ERROR' "$L/syslog-$tag.txt" | grep -vc 'page_size violated') compaction=$(grep -c 'Compacting\|Compacted' "$L/syslog-$tag.txt")"; }
first=1
for tp in $TPAIRS; do
  w=${tp%%:*}; f=${tp##*:}
  if [ $first = 1 ]; then note "THRESHOLDS phase=$f source=yaml | $(JX thresholds)"; first=0
  else note "THRESHOLDS phase=$f source=jmx-set($w,$f) | $(JX setpage "$w" "$f")"; fi
  note "PHASE-START T=$f ms=$(nowms)"
  for r in $(seq 1 "$REPS"); do onequery "$f" Q1 500 none "$r"; done
  for r in $(seq 1 "$REPS"); do onequery "$f" Q2 2000 none "$r"; done
  for r in $(seq 1 "$REPS"); do onequery "$f" Q3 off none "$r"; done
  for r in $(seq 1 "$REPS"); do onequery "$f" Q4 "$BIG" "$BIG" "$r"; done
  for r in $(seq 1 "$REPS"); do onequery "$f" Q5 "$BIG" "$((BIG + 1))" "$r"; done
  note "PHASE-END T=$f ms=$(nowms) thresholds_now | $(JX thresholds)"
done
note "QUERY-PHASE-END end_ms=$(nowms)"
stop_poller
note "STATS after-queries | $(stats)"
tail -c +$((QOFF + 1)) "$N/logs/system.log" > "$L/syslog-query-phase.txt"
grep '^ERROR' "$L/syslog-query-phase.txt" | grep 'page_size violated' | cut -c1-300 > "$L/error-pagesize-lines.txt"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v 'page_size violated' | cut -c1-300 | head -80 > "$L/error-warn-other.txt"
note "PAGESIZE ERROR lines in query phase: $(wc -l < "$L/error-pagesize-lines.txt" | tr -d ' '); OTHER ERROR/WARN lines (whole log): $(wc -l < "$L/error-warn-other.txt" | tr -d ' '); java.lang.OutOfMemoryError: $(grep -c java.lang.OutOfMemoryError "$N/logs/system.log" "$L/node.out" | tr '\n' ' ')"
stop_node
trap - EXIT; finish
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ')"
