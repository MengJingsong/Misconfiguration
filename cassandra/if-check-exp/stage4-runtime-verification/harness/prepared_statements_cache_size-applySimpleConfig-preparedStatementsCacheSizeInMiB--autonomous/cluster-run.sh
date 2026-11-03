#!/usr/bin/env bash
# Cluster tier (B3, amended 2026-10-25) of prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous: one node lifetime.
# usage: cluster-run.sh <label> <value: 0MiB | 2MiB | 32MiB | auto> <mode: startfail | main | control>
#   startfail  start with the value and wait up to 120 s for the daemon to exit (B3e)
#   main       schema, baseline histogram, NSTMT distinct PREPAREs in batches of 1000 with sjk samples between, wait 65 s, final reads (B3c-B3e)
#   control    B3h: statements 0..499, sample, then the same 500 texts re-prepared 40 times, sample, wait 65 s, final reads
# Env: C (clone, default $W/cassandra-run10), OUT (log root), NSTMT (default 20000), WAIT_AFTER (default 65).
# Node data under $W/node-psca (wiped before and after). One node, 127.0.0.1. Needs: source ~/Library/Caches/stage4/env.sh.
set -uo pipefail
LABEL=$1; VAL=$2; MODE=$3
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run10}; N=$W/node-psca
OUT=${OUT:-$W/logs/prepared_statements_cache_size-applySimpleConfig/cluster}; NSTMT=${NSTMT:-20000}; WAIT_AFTER=${WAIT_AFTER:-65}
L=$OUT/$LABEL; mkdir -p "$L"; rm -rf "$L"/*
export CASSANDRA_HOME=$C
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
note() { echo "$*" >> "$L/summary.txt"; log "$*"; }
pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null && { log "ABORT: a CassandraDaemon is already running"; exit 1; }
for p in 7000 7199 9042 9091; do lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1 && { log "ABORT: port $p busy"; exit 1; }; done
note "run $LABEL prepared_statements_cache_size=$VAL mode=$MODE NSTMT=$NSTMT clone=$(git -C "$C" rev-parse HEAD) $(date +%s)"
df -h "$W" | tail -1 >> "$L/commands.log"
# node directories and configuration (B3a amended)
rm -rf "$N"; mkdir -p "$N"/{data,commitlog,hints,saved_caches,cdc_raw,logs}; cp -R "$C/conf" "$N/conf"
Y=$N/conf/cassandra.yaml
grep -v -E '^(prepared_statements_cache_size|data_file_directories|commitlog_directory|hints_directory|saved_caches_directory|cdc_raw_directory):' "$C/conf/cassandra.yaml" > "$Y"
{ echo; echo "# stage-4 overrides ($LABEL)"
  echo "data_file_directories:"; echo "    - $N/data"
  echo "commitlog_directory: $N/commitlog"; echo "hints_directory: $N/hints"
  echo "saved_caches_directory: $N/saved_caches"; echo "cdc_raw_directory: $N/cdc_raw"
  if [ "$VAL" = auto ]; then echo "prepared_statements_cache_size:"; else echo "prepared_statements_cache_size: $VAL"; fi; } >> "$Y"
tail -9 "$Y" > "$L/yaml-overrides.txt"
log "+ MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs bin/cassandra -f"
( cd "$C" && MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_CONF="$N/conf" CASSANDRA_LOG_DIR="$N/logs" exec bin/cassandra -f ) > "$L/node.out" 2>&1 < /dev/null &
NPID=$!; log "node launcher pid $NPID"
stop_node() {
  log "stopping node"
  if kill -0 "$NPID" 2>/dev/null; then
    ( cd "$C" && bin/nodetool drain ) >> "$L/commands.log" 2>&1 & DRP=$!
    for i in $(seq 1 60); do kill -0 "$DRP" 2>/dev/null || break; sleep 1; done; kill "$DRP" 2>/dev/null; log "drain done or bounded"
    kill "$NPID" 2>/dev/null; for i in $(seq 1 60); do kill -0 "$NPID" 2>/dev/null || break; sleep 1; done
    kill -9 "$NPID" 2>/dev/null
  fi
  pkill -9 -f 'org.apache.cassandra.service.CassandraDaemon' 2>/dev/null
  sleep 2; if pgrep -f org.apache.cassandra.service.CassandraDaemon >/dev/null; then log "WARNING: CassandraDaemon still running"; else log "no CassandraDaemon left"; fi; }
finish() {
  [ -f "$N/logs/system.log" ] && cp "$N/logs/system.log" "$L/system.log"
  du -sh "$N/data" "$N/commitlog" >> "$L/commands.log" 2>&1
  rm -rf "$N"; log "node dir wiped"; }
trap 'stop_node; finish' EXIT
if [ "$MODE" = startfail ]; then
  res=timeout
  for i in $(seq 1 60); do
    kill -0 "$NPID" 2>/dev/null || { res=exited; break; }
    if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1'); then res=started; break; fi
    sleep 2
  done
  note "STARTFAIL result=$res after_s=$((i*2))"
  { grep -h 'prepared_statements_cache_size option' "$L/node.out" | head -5 | sed 's/^/console: /'
    grep -h 'prepared_statements_cache_size option' "$N/logs/system.log" 2>/dev/null | grep -v 'Node configuration' | head -5 | sed 's/^/system.log: /'; } | cut -c1-400 > "$L/startfail.txt"
  cat "$L/startfail.txt" >> "$L/summary.txt"
  exit 0
fi
ok=0
for i in $(seq 1 180); do
  kill -0 "$NPID" 2>/dev/null || { log "ABORT: node died during start"; exit 1; }
  if (cd "$C" && bin/nodetool status 2>/dev/null | grep -q '^UN  127.0.0.1') && [ "$(cd "$C" && bin/nodetool statusbinary 2>/dev/null)" = running ]; then ok=1; break; fi
  sleep 2
done
[ $ok = 1 ] || { log "ABORT: node not UN/running within 360 s"; exit 1; }
DPID=$(pgrep -f org.apache.cassandra.service.CassandraDaemon | head -1); log "node UN, statusbinary running; daemon pid $DPID"
RB=$(grep -o 'Initialized prepared statement caches with [0-9]* MiB' "$N/logs/system.log" | head -1)
note "READBACK $RB"
case $VAL in auto) EXP=10;; *) EXP=${VAL%MiB};; esac
[ "$RB" = "Initialized prepared statement caches with $EXP MiB" ] || { note "READBACK MISMATCH expected $EXP MiB"; exit 1; }
sjk() { (cd "$C" && bin/nodetool sjk mx -mg -b "org.apache.cassandra.metrics:type=CQL,name=$1" -f "$2" 2>&1) | tr -d '\r' | grep -E '^[0-9]+$' | tail -1; }
sample() { local c e; c=$(sjk PreparedStatementsCount Value); e=$(sjk PreparedStatementsEvicted Count); echo "$1,$(date +%s),$c,$e" >> "$L/samples.csv"; log "sample $1 count=$c evicted=$e"; }
histo() { jmap -histo:live "$DPID" > "$L/histo-$1.txt" 2>&1; jcmd "$DPID" GC.heap_info > "$L/heapinfo-$1.txt" 2>&1
  local tot prep; tot=$(grep -E '^Total' "$L/histo-$1.txt"); prep=$(grep -E 'org\.apache\.cassandra\.cql3\.QueryHandler\$Prepared$' "$L/histo-$1.txt")
  note "HISTO $1 total: $tot | Prepared: $prep"; grep -E 'QueryHandler\$Prepared|SelectStatement' "$L/histo-$1.txt" > "$L/histo-excerpt-$1.txt"; }
client() { log "+ prep.py $*"; local r; r=$(python3 -I "$H/prep.py" "$@" 2>>"$L/client.err" | grep '^RESULT'); note "${r:-RESULT missing (see client.err)}"; }
echo "prepares_done,epoch_s,count,evicted" > "$L/samples.csv"
client schema
histo 0-baseline
sample 0
if [ "$MODE" = main ]; then
  for ((b = 0; b < NSTMT; b += 1000)); do
    e=$((b + 1000)); [ $e -gt $NSTMT ] && e=$NSTMT
    client load $b $e
    sample $e
  done
else
  client load 0 500
  sample 500
  client reprep 0 500 40
  sample 20500
fi
log "waiting $WAIT_AFTER s (per-minute discard warning, B3e amended)"; sleep "$WAIT_AFTER"
sample final
histo 1-end
grep -h 'prepared statements discarded in the last minute' "$N/logs/system.log" > "$L/discard-warnings.txt"
note "DISCARD-WARNINGS $(wc -l < "$L/discard-warnings.txt" | tr -d ' ') first: $(head -1 "$L/discard-warnings.txt" | cut -c1-200)"
grep -E '^(ERROR|WARN)' "$N/logs/system.log" | grep -v 'discarded in the last minute' | cut -c1-300 | head -50 > "$L/error-warn.txt"
note "OTHER ERROR/WARN lines: $(wc -l < "$L/error-warn.txt" | tr -d ' ')"
trap - EXIT; stop_node; finish
