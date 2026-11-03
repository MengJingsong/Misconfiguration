#!/usr/bin/env bash
# Cluster tier (B3, as amended 2026-10-26) of items_per_collection-doAdd-elements_size--autonomous: one node lifetime, three arms.
# usage: cluster-run.sh [T1 T2 REPS]      run 1: no arguments = 1000 10000 200 (as filed); shakedown only: e.g. 50 500 20
#   arm A  T = T1 from the yaml (warn T1/2), table probe.s<T1>,  workload W = T1
#   arm B  T = T2 set at runtime (nodetool setguardrailsconfig items_per_collection_threshold T2 T2/2), table probe.s<T2>, W = T2
#   arm R  disabled reference, -1/-1 at runtime, table probe.sref, W = T1
#   each arm: ipc.py setup; nodetool disableautocompaction; phases i, ii, iii, iv, each followed by tablestats (memtable before
#   the flush), nodetool flush, tablestats, the table directory's bytes, and the system.log lines the phase wrote.
# Env: C (clone, default $W/cassandra-run31), OUT (log dir), IPC_NODE (node dir, default $W/node-ipc; wiped before and after),
#      IPC_PLAN (run1 = phases i ii iii iv, the default; run2 = i ii iii iiib iv, amendments B3c-B3e of 2026-10-28).
# Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
T1=${1:-1000}; T2=${2:-10000}; REPS=${3:-200}
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run31}; N=${IPC_NODE:-$W/node-ipc}
PLAN=${IPC_PLAN:-run1}; case $PLAN in run1) PHASES='i ii iii iv';; run2) PHASES='i ii iii iiib iv';; *) echo "bad IPC_PLAN"; exit 2;; esac
OUT=${OUT:-$W/logs/items_per_collection-doAdd-elements_size--autonomous/cluster}
L=$OUT; mkdir -p "$L"; rm -rf "${L:?}"/*
export CASSANDRA_HOME=$C
DPAT='cassandra.service.Cassandra''Daemon'      # split so this script's own command line never matches
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f "$DPAT" >/dev/null && { log "ABORT: a Cassandra daemon is already running"; exit 1; }
for p in 7000 7199 9042; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "RUN T1=$T1 T2=$T2 REPS=$REPS plan=$PLAN phases=$PHASES node=$N clone=$(git -C "$C" rev-parse HEAD) start_epoch=$(date +%s)"
df -h "$W" | tail -1 >> "$L/commands.log"
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(authenticator|authorizer|read_request_timeout|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory|listen_address|rpc_address):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides (items_per_collection)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  echo "listen_address: 127.0.0.1"; echo "rpc_address: 127.0.0.1"
  echo "authenticator: PasswordAuthenticator"; echo "authorizer: CassandraAuthorizer"
  echo "read_request_timeout: 60000ms"
  echo "items_per_collection_warn_threshold: $((T1 / 2))"; echo "items_per_collection_fail_threshold: $T1"; } >> "$Y"
tail -16 "$Y" > "$L/yaml-overrides.txt"
diff <(grep -v '^ *#' "$C/conf/cassandra.yaml" | grep -v '^\s*$') <(grep -v '^ *#' "$Y" | grep -v '^\s*$') > "$L/yaml-diff.txt"
log "+ MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
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
grep -m1 -o 'JVM Arguments: .*' "$N/logs/system.log" | grep -o -- '-Xm[sxn][0-9]*[GM]' | tr '\n' ' ' > "$L/jvmargs-excerpt.txt"; note "JVMARGS $(cat "$L/jvmargs-excerpt.txt")"
grep -E 'items_per_collection_(warn|fail)_threshold|authenticator=|authorizer=' "$N/logs/system.log" | head -1 | grep -o -E 'authenticator=[^;]*;|authorizer=[^;]*;|items_per_collection_(warn|fail)_threshold=[^;]*;' | tr '\n' ' ' > "$L/config-line.txt"
note "CONFIG $(cat "$L/config-line.txt")"
NT() { (cd "$C" && bin/nodetool "$@"); }
readback() { NT getguardrailsconfig items_per_collection_threshold > "$L/readback-$1.txt" 2>&1; local g; g=$(grep -E '^\[' "$L/readback-$1.txt" | tr -d '\n'); note "GUARDRAIL-READBACK $1 [fail, warn] | $g"; }
client() { log "+ ipc.py $*"; local r; r=$(python3 -I "$H/ipc.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); note "${r:-RESULT missing (see client.err)}"; }
memtable() { NT tablestats "probe.$1" 2>&1 | grep -E 'Memtable data size:|SSTable count:|Space used \(live\):' | sed 's/^[[:space:]]*//' | tr '\n' ';'; }
tdir() { ls -d "$N/data/probe/$1-"* 2>/dev/null | head -1; }
phase() { # $1 arm $2 phase $3 W $4 table
  local arm=$1 ph=$2 w=$3 tab=$4 off; off=$(wc -c < "$N/logs/system.log" | tr -d ' ')
  if [ "$ph" = iiib ]; then client phase iiibseed "$w" "$tab"; note "STATS $arm iiib seeded | $(memtable "$tab")"; fi
  client phase "$ph" "$w" "$tab" "$REPS"
  note "STATS $arm $ph before-flush | $(memtable "$tab")"
  log "+ nodetool flush probe $tab"; NT flush probe "$tab" >> "$L/commands.log" 2>&1; note "FLUSH-RC $arm $ph $?"
  note "STATS $arm $ph after-flush | $(memtable "$tab")"
  note "BYTES $arm $ph | $(python3 -I "$H/ipc.py" bytes "$(tdir "$tab")" | grep '^RESULT')"
  tail -c +$((off + 1)) "$N/logs/system.log" | grep 'items_per_collection' > "$L/guardrail-$arm-$ph.txt"
  note "LOGLINES $arm $ph | write-fail=$(grep -c 'violated: Detected collection v with' "$L/guardrail-$arm-$ph.txt") write-warn=$(grep '^WARN' "$L/guardrail-$arm-$ph.txt" | grep -c 'violated: Detected collection v with') flush-lines=$(grep -c ' in row ' "$L/guardrail-$arm-$ph.txt") flush-first: $(grep -m1 ' in row ' "$L/guardrail-$arm-$ph.txt" | grep -o 'Detected collection v in row .*' | cut -c1-200)"
  case $ph in
    i)   client keys "$tab" 1000 "$REPS";;
    ii)  client card "$tab" 1;;
    iii) client card "$tab" 2;;
    iiib) client card "$tab" 3;;
    iv)  client keys "$tab" 2000 "$REPS"; client card "$tab" 2000;;
  esac; }
arm() { # $1 arm $2 W $3 table
  local arm=$1 w=$2 tab=$3
  note "ARM $arm W=$w table=probe.$tab start_epoch=$(date +%s)"
  readback "$arm"
  client setup "$tab"
  log "+ nodetool disableautocompaction probe $tab"; NT disableautocompaction probe "$tab" >> "$L/commands.log" 2>&1
  note "STATS $arm base | $(memtable "$tab")"
  note "BYTES $arm base | $(python3 -I "$H/ipc.py" bytes "$(tdir "$tab")" | grep '^RESULT')"
  for ph in $PHASES; do phase "$arm" "$ph" "$w" "$tab"; done
  note "ARM-END $arm end_epoch=$(date +%s)"; }
arm A "$T1" "s$T1"
log "+ nodetool setguardrailsconfig items_per_collection_threshold $T2 $((T2 / 2))"
NT setguardrailsconfig items_per_collection_threshold "$T2" "$((T2 / 2))" >> "$L/commands.log" 2>&1
arm B "$T2" "s$T2"
log "+ nodetool setguardrailsconfig items_per_collection_threshold -1 -1"
NT setguardrailsconfig items_per_collection_threshold -1 -1 >> "$L/commands.log" 2>&1
arm R "$T1" "sref"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v 'items_per_collection' | cut -c1-300 | head -50 > "$L/error-warn.txt"
note "OTHER ERROR/WARN lines: $(wc -l < "$L/error-warn.txt" | tr -d ' ')"
grep -E 'Enqueuing flush|Completed flushing|Flushing largest' "$N/logs/system.log" | grep -i 'probe' | cut -c1-250 > "$L/flush-lines.txt"
note "FLUSH-LOG-LINES probe: $(wc -l < "$L/flush-lines.txt" | tr -d ' '); automatic (Flushing largest): $(grep -c 'Flushing largest' "$L/flush-lines.txt")"
trap - EXIT; stop_node; finish
note "END end_epoch=$(date +%s)"
