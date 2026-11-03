#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous:
# one node lifetime.
# usage: cluster-run.sh <label> <value: e.g. 4MiB | 32MiB | auto | 412MiB> <mode: main | control> <N>
#   main     schema, I_base, baseline, R0, prep.py load 1..N, wait, I_end, final readings, R
#   control  as main, but the load is 1..N/2, half-point readings (no clear), then N/2+1..N (B3e step 7)
# Env: C (clone, default $W/cassandra-run30), OUT (log root), WAIT_AFTER (default 120, B3e step 4).
# Node data under $W/node-pscs (wiped before and after). One node, 127.0.0.1. Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
LABEL=$1; VAL=$2; MODE=$3; NST=$4
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run30}; N=$W/node-pscs
OUT=${OUT:-$W/logs/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/cluster}
WAIT_AFTER=${WAIT_AFTER:-120}
L=$OUT/$LABEL; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
BMJAR=$C/build/lib/jars/byteman-4.0.20.jar
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN $LABEL prepared_statements_cache_size=$VAL mode=$MODE N=$NST clone=$(git -C "$C" rev-parse HEAD) start_epoch=$(date +%s)"
df -h "$W" | tail -1 >> "$L/commands.log"
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(prepared_statements_cache_size|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
  if [ "$VAL" = auto ]; then echo "prepared_statements_cache_size:"; else echo "prepared_statements_cache_size: $VAL"; fi; } >> "$Y"
tail -11 "$Y" > "$L/yaml-overrides.txt"
diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff.txt"
JX="-javaagent:$BMJAR=script:$H/pscache.btm,listener:true"
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs JVM_EXTRA_OPTS=$JX bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" JVM_EXTRA_OPTS="$JX" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
stop_node() {
  log "stopping node"
  if kill -0 "$NPID" 2>/dev/null; then
    ( cd "$C" && bin/nodetool stopdaemon ) >> "$L/commands.log" 2>&1 & SDP=$!
    for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill "$SDP" 2>/dev/null
    if kill -0 "$NPID" 2>/dev/null; then log "still alive after 60 s: kill"; kill "$NPID"; sleep 10; kill -9 "$NPID" 2>/dev/null; fi
  fi
  sleep 2; local left; left=$(pgrep -f "$DPAT")
  if [ -n "$left" ]; then log "WARNING: daemon still running ($left): kill -9"; kill -9 $left; sleep 2; fi
  pgrep -f "$DPAT" >/dev/null && log "WARNING: daemon still running" || log "no Cassandra daemon left"; }
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
DPID=$(pgrep -f "$DPAT" | head -1); log "node UN, statusbinary running; daemon pid $DPID"
grep -m1 -o 'JVM Arguments: .*' "$N/logs/system.log" | grep -o -- '-Xm[sxn][0-9]*[GM]\|-javaagent:[^,]*byteman[^,]*' | tr '\n' ' ' > "$L/jvmargs-excerpt.txt"; note "JVMARGS $(cat "$L/jvmargs-excerpt.txt")"
RB=$(grep -o 'Initialized prepared statement caches with [0-9]* MiB' "$N/logs/system.log" | head -1)
note "READBACK $RB"
case $VAL in auto) EXP=10;; *) EXP=${VAL%MiB};; esac
[ "$RB" = "Initialized prepared statement caches with $EXP MiB" ] || { note "READBACK MISMATCH expected $EXP MiB"; exit 1; }
grep -i 'byteman\|TypeException\|ParseException' "$L/node.out" | head -5 >> "$L/commands.log"
client() { log "+ prep.py $*"; local r; r=$(python3 -I "$H/prep.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); note "${r:-RESULT missing (see client.err)}"; }
pscache() { client trigger "$1"; sleep 1; local l; l=$(grep '^PSCACHE' "$L/node.out" | tail -$2 | tr '\n' ' '); note "PSCACHE-$3 $l"; }
histo() { jcmd "$DPID" GC.class_histogram > "$L/histo-$1.txt" 2>&1
  local tot prep; tot=$(grep -E '^Total' "$L/histo-$1.txt"); prep=$(grep -E 'org\.apache\.cassandra\.cql3\.QueryHandler\$Prepared( |$)' "$L/histo-$1.txt" | head -1)
  note "HISTO $1 | $tot | $prep"; }
heap() { jcmd "$DPID" GC.run > /dev/null 2>&1; sleep 5; jcmd "$DPID" GC.heap_info > "$L/heapinfo-$1.txt" 2>&1
  note "HEAPINFO $1 | $(grep -m1 -E 'heap +total' "$L/heapinfo-$1.txt" | sed 's/^ *//')"; }
client schema
pscache read 1 base
histo 0-base
heap 0-base
client metrics
log "R0 (noise): histogram, clear, histogram"
histo r0-before; pscache clear 2 r0; histo r0-after
if [ "$MODE" = main ]; then
  client load 1 "$NST" "$L/samples.csv"
else
  H2=$((NST / 2))
  client load 1 "$H2" "$L/samples.csv"
  pscache read 1 half
  histo 1-half
  heap 1-half
  client load $((H2 + 1)) "$NST" "$L/samples.csv"
fi
log "waiting $WAIT_AFTER s (B3e step 4)"; sleep "$WAIT_AFTER"
pscache read 1 end
histo 2-end
heap 2-end
client metrics
grep -h 'prepared statements discarded in the last minute' "$N/logs/system.log" > "$L/discard-warnings.txt"
note "DISCARD-WARNINGS $(wc -l < "$L/discard-warnings.txt" | tr -d ' ') first: $(head -1 "$L/discard-warnings.txt" | cut -c1-220)"
log "R: histogram, clear, histogram"
histo r-before; pscache clear 2 r; histo r-after; pscache read 1 after-r
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v 'discarded in the last minute' | cut -c1-300 | head -50 > "$L/error-warn.txt"
note "OTHER ERROR/WARN lines: $(wc -l < "$L/error-warn.txt" | tr -d ' ')"
grep '^PSCACHE' "$L/node.out" > "$L/pscache-lines.txt"
trap - EXIT; stop_node; finish
note "END $LABEL end_epoch=$(date +%s)"
