#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of sai_vector_term_size_fail_threshold-add-value--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; cluster-run.sh            (run 1: arms A C D E)
#        ARMS="A C" OUT=<dir> cluster-run.sh                               (shakedown)
# One node from the clone per arm (own conf and data under $W/node-vts, wiped before and after), MAX_HEAP_SIZE=4G,
# memtable_heap_space 2048MiB, thresholds per arm in cassandra.yaml; arm E adds PasswordAuthenticator + CassandraAuthorizer.
# Per arm: start; setup; JMX + class histogram; load (D: two passes); JMX + histogram; ANN; count; tablestats; log grep;
# drain; stopdaemon; check no daemon left; copy logs; wipe.
# Env: C (clone, default $W/cassandra-run40), OUT (log dir), ARMS, LOADCONC (default 8); VTS_ROWS (probe.py, shakedown only).
set -uo pipefail
ARMS=${ARMS:-"A C D E"}; LOADCONC=${LOADCONC:-8}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run40}; N=$W/node-vts
OUT=${OUT:-$W/logs/sai_vector_term_size_fail_threshold-add-value--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN ARMS=$ARMS LOADCONC=$LOADCONC clone=$(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') start_epoch=$(date +%s)"
NT() { (cd "$C" && bin/nodetool "$@"); }
MB='org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=vt,table=t,index=t_v_idx,scope=IndexMetrics,name='
JMX() { java "$H/JmxGet.java" localhost:7199 Value "${MB}MemtableIndexBytes" "${MB}LiveMemtableIndexWriteCount" 2>&1 \
        | sed -e "s/^.*name=MemtableIndexBytes Value=/MemtableIndexBytes=/" -e "s/^.*name=LiveMemtableIndexWriteCount Value=/LiveMemtableIndexWriteCount=/" | tr '\n' ' '; }
NPID=; DP=; ARM=
stop_node() {
  [ -z "$NPID" ] && return
  log "stopping node (launcher pid $NPID)"
  if kill -0 "$NPID" 2>/dev/null; then
    NT drain >> "$L/commands.log" 2>&1; log "drain rc=$?"
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
  [ -z "$ARM" ] && return
  local A=$L/arm$ARM; mkdir -p "$A"
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$A/system.log"
  for g in "$N"/gc.log*; do [ -f "$g" ] && cp "$g" "$A/"; done
  rm -rf "$N"; log "arm $ARM: node dir wiped"; ARM=; }
trap 'stop_node; finish' EXIT

for X in $ARMS; do
  case $X in
    A) WARN=16KiB; FAIL=32KiB; PASSES=1; AUTH= ;;
    C) WARN=2KiB;  FAIL=4KiB;  PASSES=1; AUTH= ;;
    D) WARN=2KiB;  FAIL=4KiB;  PASSES=2; AUTH= ;;
    E) WARN=2KiB;  FAIL=4KiB;  PASSES=1; AUTH=auth ;;
    *) log "ABORT: unknown arm $X"; exit 1 ;;
  esac
  ARM=$X; A=$L/arm$X; mkdir -p "$A"
  note "ARM $X warn=$WARN fail=$FAIL passes=$PASSES auth=${AUTH:-none} epoch=$(date +%s)"
  rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
  Y=$N/conf/cassandra.yaml
  grep -v -E '^(data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address|memtable_heap_space|authenticator|authorizer|sai_vector_term_size_warn_threshold|sai_vector_term_size_fail_threshold):' "$C/conf/cassandra.yaml" > "$Y"
  { echo; echo "# stage-4 overrides (sai_vector_term_size_fail_threshold, arm $X)"
    echo "data_file_directories:"; echo "    - $N/data"
    echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
    echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
    echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
    echo "memtable_heap_space: 2048MiB"
    echo "sai_vector_term_size_warn_threshold: $WARN"; echo "sai_vector_term_size_fail_threshold: $FAIL"
    if [ -n "$AUTH" ]; then echo "authenticator: PasswordAuthenticator"; echo "authorizer: CassandraAuthorizer"
    else echo "authenticator: AllowAllAuthenticator"; echo "authorizer: AllowAllAuthorizer"; fi; } >> "$Y"
  sed -n '/# stage-4 overrides/,$p' "$Y" > "$A/yaml-overrides.txt"
  echo "-Xlog:gc*:file=$N/gc.log:time,uptime" >> "$N/conf/jvm-server.options"
  log "+ MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
  ( cd "$C" && MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) >> "$A/node.out" 2>&1 < /dev/null &
  NPID=$!; log "node launcher pid $NPID"
  ok=0
  for i in $(seq 1 180); do
    kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
    if NT status 2>/dev/null | grep -q '^UN  127.0.0.1' && [ "$(NT statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
    sleep 2
  done
  [ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
  DP=$(pgrep -f "$DPAT" | head -1); log "node UN, statusbinary running; daemon pid $DP"
  SL=$N/logs/system.log
  RB() { grep -m1 'Node configuration:' "$SL" | grep -o -E "(\[|; )$1=[^;]*" | head -1 | sed 's/^[[; ]*//'; }   # exact key (fixed after shakedown 1)
  note "READBACK $X | $(RB sai_vector_term_size_warn_threshold) $(RB sai_vector_term_size_fail_threshold) $(RB authenticator) $(RB authorizer) $(RB memtable_heap_space) heap=$(grep -m1 -o 'JVM Arguments: .*' "$SL" | grep -o -E -- '-Xm[sx][0-9]*[GM]|-XX:\+UseG1GC' | tr '\n' ' ')"
  PY() { python3 -I "$H/probe.py" "$@" 2>>"$A/client.err" | grep '^RESULT' || echo "RESULT missing (see client.err)"; }
  HISTO() { jcmd "$DP" GC.class_histogram > "$A/histo-$1.txt" 2>&1
    awk '/^Total/ {t=$3} $4=="[F" {f=$3} $4=="[B" {b=$3} END {printf "live_total=%s float_arr=%s byte_arr=%s", t, f, b}' "$A/histo-$1.txt"; }
  stats() { NT tablestats vt.t 2>&1 | grep -E 'SSTable count:|Memtable cell count:|Memtable data size:|Memtable on heap memory used:|Memtable off heap memory used:' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }
  note "SETUP $X | $(PY setup $AUTH)"
  note "JMX before $X | $(JMX)"
  note "HISTO before $X | $(HISTO before)"
  log "+ probe.py load $PASSES $LOADCONC $AUTH"
  PY load "$PASSES" "$LOADCONC" $AUTH | while read -r line; do note "LOAD $X | $line"; done
  note "JMX after $X | $(JMX)"
  note "HISTO after $X | $(HISTO after)"
  note "ANN $X | $(PY ann $AUTH)"
  note "COUNT $X | $(PY count $AUTH)"
  note "STATS $X | $(stats)"
  note "LOGLINES $X | too_large=$(grep -c 'too large and cannot be indexed' "$SL") first=$(grep -m1 -o 'Term in column.*' "$SL" | cut -c1-200)"
  note "ERRORS $X | ERROR=$(grep -c '^ERROR' "$SL") OOM=$(cat "$SL" "$A/node.out" | grep -cF java.lang.OutOfMemoryError) guardrail_lines=$(grep -c 'Guardrail sai_vector_term_size' "$SL")"
  grep -E '^(ERROR|WARN)' "$SL" | cut -c1-300 | head -60 > "$A/error-warn.txt"
  stop_node
  finish
done
trap - EXIT
note "END end_epoch=$(date +%s) daemons_left=$(pgrep -f "$DPAT" | wc -l | tr -d ' ') clone_status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ')"
