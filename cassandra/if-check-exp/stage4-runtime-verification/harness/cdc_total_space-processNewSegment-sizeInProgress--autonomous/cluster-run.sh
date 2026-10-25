#!/usr/bin/env bash
# Stage 4 run 1, cluster tier: cdc_total_space-processNewSegment-sizeInProgress--autonomous, case B3.
#   cluster-run.sh <label>   one cell, end to end.  Labels: <nb|b><cap>-r<rep>  (cap in MiB: 128 256 4096; "b" = blocking, "nb" = non-blocking)
#                            plainnb128-r<rep> (non-CDC table k.tp, non-blocking, cap 128)   chk-b160 (instrument check, not in the matrix)
#   cluster-run.sh all       R1 nb128 x2, R2 nb256 x2, R3 nb4096 x1, R4 b128 x2, R5 b4096 x1, R6 b256 x2, plain x1
# One node from CLONE on its own loopback address and ports (another agent shares the host); every node directory on
# local disk under $R; logs under $L/<label>/. Kills only its own PIDs.
set -Euo pipefail
ulimit -n 100000
C=${CLONE:-$HOME/s4-cdc/clone}
HARNESS=${HARNESS:-$HOME/s4-cdc/harness}
L=${LOGDIR:-$HOME/s4-cdc/logs/cluster}
R=$HOME/s4-cdc/run
BM=$C/build/lib/jars
IP=127.0.0.37; JMXP=7237
export MAX_HEAP_SIZE=1G
D=""; SAMPLER_PID=""; DU_PID=""; STRESS_PID=""; FLUSH_PID=""
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$D/summary.txt"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
pid_up() { [ -s "$C/cassandra.pid" ] && kill -0 "$(cat "$C/cassandra.pid")" 2> /dev/null; }
cleanup() {
  local rc=$?; trap - EXIT ERR
  [ -n "$FLUSH_PID" ] && kill "$FLUSH_PID" 2> /dev/null || true
  [ -n "$STRESS_PID" ] && kill "$STRESS_PID" 2> /dev/null || true
  [ -n "$DU_PID" ] && kill "$DU_PID" 2> /dev/null || true
  [ -n "$SAMPLER_PID" ] && kill -TERM "$SAMPLER_PID" 2> /dev/null || true
  if pid_up; then local p; p=$(cat "$C/cassandra.pid"); (cd "$C" && bin/nodetool stopdaemon) > /dev/null 2>&1 || true
    for _ in $(seq 60); do kill -0 "$p" 2> /dev/null || break; sleep 1; done
    kill -0 "$p" 2> /dev/null && { kill -9 "$p"; sleep 2; }; fi
  exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

nt() { (cd "$C" && bin/nodetool "$@" 2>&1); }
cql() { (cd "$C" && timeout 60 bin/cqlsh "$IP" "$@" 2>&1); }
node_ready() { pid_up && [ "$(nt statusbinary)" = running ] && nt status | grep -q '^UN'; }
links() { ls "$R/cdc_raw" 2> /dev/null | grep -c -E '^CommitLog-[0-9]+-[0-9]+\.log$' || true; }
warn_count() { grep -c '^WARN.*Rejecting mutation to keyspace' "$C/logs/system.log" 2> /dev/null || true; }
freed_count() { grep -c 'Freed up' "$C/logs/debug.log" 2> /dev/null || true; }
phase() { echo "$(now),$1" >> "$D/phases.csv"; log "phase $1"; }
last_row() { tail -1 "$D/sampler.csv"; }
listing() { ls -l "$R/cdc_raw" 2> /dev/null | awk 'NR>1{print $9":"$5}' | tr '\n' ' '; }

probe_cdc() {   # one small CDC-tracked insert via cqlsh -> 0 if accepted
  local out; out=$(cql -e "INSERT INTO k.t (id, v) VALUES ($((3000000000 + RANDOM)), 0xdeadbeef)") && ! echo "$out" | grep -qi -E 'error|failure|exception'
}

cell() {
  local label=$1 mode cap rep kind=cdc tbl=t prof=cdc-rows-64k.yaml
  rep=${label##*-r}; local head=${label%-r*}
  case $head in
    b[0-9]*)       mode=blocking;    cap=${head#b} ;;
    nb[0-9]*)      mode=nonblocking; cap=${head#nb} ;;
    plainnb[0-9]*) mode=nonblocking; cap=${head#plainnb}; kind=plain; tbl=tp; prof=plain-rows-64k.yaml ;;
    chk-b[0-9]*)   mode=blocking;    cap=${head#chk-b}; rep=1 ;;
    *) echo "bad label $label" >&2; exit 2 ;;
  esac
  local rows=32768 rate=200 chkrows=${CHKROWS:-}
  [ "$label" = "chk-b160" ] && rows=${chkrows:-6144}
  D=$L/$label; [ -e "$D" ] && mv "$D" "$D.attempt-$(date +%s)"; mkdir -p "$D"; : > "$D/summary.txt"; : > "$D/phases.csv"
  exec > >(tee -a "$D/session.log") 2>&1
  note "== $label: mode=$mode cap=${cap}MiB table=k.$tbl rows=$rows (=$((rows / 16)) MiB) rate=$rate/s heap=$MAX_HEAP_SIZE ip=$IP jmx=$JMXP"
  cd "$C"
  pid_up && fail "a node from this clone is running"
  ( cd "$HARNESS" && sha256sum -c SHA256SUMS > /dev/null ) || fail "harness copy differs"
  [ "$(git describe --tags)" = cassandra-5.0.9 ] || fail "clone not at the tag"
  [ "$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)" -ge 20 ] || fail "less than 20 GB free"
  ss -ltn | grep -q -E "${IP//./\\.}:|:${JMXP}\b" && fail "my address or JMX port is busy"
  # --- config (own clone only)
  git checkout -q conf/cassandra.yaml conf/cassandra-env.sh
  sed -i "s/^JMX_PORT=\"7199\"/JMX_PORT=\"$JMXP\"/" conf/cassandra-env.sh
  sed -i "s/^cdc_enabled: false\$/cdc_enabled: true/; s/^listen_address: localhost\$/listen_address: $IP/; s/^rpc_address: localhost\$/rpc_address: $IP/; s/- seeds: \"127.0.0.1:7000\"/- seeds: \"$IP:7000\"/" conf/cassandra.yaml
  {
    echo "cdc_total_space: ${cap}MiB"
    echo "cdc_free_space_check_interval: 250ms"
    echo "cdc_raw_directory: $R/cdc_raw"
    echo "commitlog_directory: $R/commitlog"
    echo "data_file_directories: [$R/data]"
    echo "hints_directory: $R/hints"
    echo "saved_caches_directory: $R/saved_caches"
    echo "commitlog_total_space: 2048MiB"
    [ "$mode" = nonblocking ] && echo "cdc_block_writes: false"
  } >> conf/cassandra.yaml
  git diff -U0 conf/cassandra.yaml conf/cassandra-env.sh | grep '^[+-][^+-]' > "$D/yaml.diff"; cat "$D/yaml.diff" >&2
  # --- reset: all node data on local disk under $R
  rm -rf "$R" cassandra.pid; mkdir -p "$R"
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then mv logs "$L/logs.before-$label.$(date +%s)"; fi; mkdir -p logs
  # --- start (Byteman observation rules only; no listener)
  local opts="-Dstage4.byteman.out=$D/cdc-verdict.txt -javaagent:$BM/byteman-4.0.20.jar=script:$HARNESS/cdc-verdict.btm"
  note "JVM_EXTRA_OPTS=$opts; ulimit -n $(ulimit -n)"
  JVM_EXTRA_OPTS="$opts" bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1
  local i=0; until node_ready; do sleep 1; i=$((i + 1)); pid_up || fail "daemon died at start (stdout.txt)"; [ $i -ge 240 ] && fail "start timeout"; done
  note "node up after ${i}s, pid $(cat cassandra.pid)"
  cql -e "SELECT name, value FROM system_views.settings WHERE name IN ('cdc_enabled','cdc_total_space','cdc_block_writes','commitlog_segment_size','commitlog_total_space','cdc_raw_directory','cdc_free_space_check_interval')" > "$D/settings.txt"
  sed 's/^/    | /' "$D/settings.txt" >&2
  grep -q "cdc_total_space *| *${cap}MiB\|cdc_total_space *| *${cap}$" "$D/settings.txt" || note "NOTE: cdc_total_space read-back differs from ${cap}MiB (settings.txt)"
  grep -q "commitlog_segment_size *| *32" "$D/settings.txt" || fail "segment size is not 32 MiB"
  nt setlogginglevel org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC DEBUG > /dev/null
  # --- schema while idle
  cql -e "CREATE KEYSPACE IF NOT EXISTS k WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE IF NOT EXISTS k.t (id bigint PRIMARY KEY, v blob) WITH cdc = true; CREATE TABLE IF NOT EXISTS k.tp (id bigint PRIMARY KEY, v blob) WITH cdc = false;" > "$D/schema.txt" || fail "schema"
  # --- samplers: 50 ms and du -sb / allocated every 2 s
  mkdir -p "$R/cdc_raw"
  python3 "$HARNESS/cdc-sampler.py" "$R/cdc_raw" "$D/sampler" 0.05 &
  SAMPLER_PID=$!
  ( while :; do echo "$(now) cdc_raw=$(du -sb "$R/cdc_raw" 2> /dev/null | cut -f1) alloc=$(du -s --block-size=1 "$R/cdc_raw" 2> /dev/null | cut -f1) commitlog=$(du -sb "$R/commitlog" 2> /dev/null | cut -f1) data=$(du -sb "$R/data" 2> /dev/null | cut -f1) free=$(df --output=avail -B1 "$HOME" | tail -1 | tr -d ' ')"; sleep 2; done ) > "$D/du.txt" 2>&1 &
  DU_PID=$!
  sleep 5; phase idle; note "idle: links=$(links) $(last_row)"
  # --- workload (B3c): 2 GiB of 64 KiB rows at 200 rows/s, nodetool flush every 10 s (about every 128 MiB)
  phase W_start; local w0; w0=$(now)
  ( while :; do sleep 10; (cd "$C" && bin/nodetool flush k "$tbl") > /dev/null 2>&1; echo "$(now),flush" >> "$D/phases.csv"; done ) &
  FLUSH_PID=$!
  log "+ cassandra-stress user profile=$prof ops(insert=1) n=$rows no-warmup -rate threads=8 throttle=$rate/s"
  (cd "$C" && tools/bin/cassandra-stress user profile="$HARNESS/$prof" "ops(insert=1)" n=$rows no-warmup -rate threads=8 throttle=$rate/s -errors retries=0 ignore -node $IP) > "$D/stress-W.txt" 2>&1 &
  STRESS_PID=$!
  while kill -0 "$STRESS_PID" 2> /dev/null; do
    sleep 2
    [ $(( $(now) - w0 )) -gt 600000 ] && { note "stress did not end in 600 s: killed"; kill "$STRESS_PID"; break; }
  done
  wait "$STRESS_PID" 2> /dev/null || true; STRESS_PID=""
  kill "$FLUSH_PID" 2> /dev/null; FLUSH_PID=""
  phase W_end
  note "stress W: $(grep -E 'Total errors|Total partitions|Op rate' "$D/stress-W.txt" | tr -s ' ' | tr '\n' '|') wall=$(( ($(now) - w0) / 1000 ))s"
  note "after workload: links=$(links) $(last_row) WARN=$(warn_count) Freed_up=$(freed_count) listing=$(listing)"
  sleep 30; phase W_plus30
  nt flush k "$tbl" > /dev/null 2>&1 || true
  sleep 3; note "final reading (W+30 s, after a last flush): links=$(links) $(last_row) WARN=$(warn_count) Freed_up=$(freed_count)"
  note "final listing: $(listing)"
  if [ "$mode" = blocking ] && [ "$kind" = cdc ] && [ "$cap" -lt 4096 ]; then
    # --- release (amendment 2026-10-25 (5)): delete the two oldest links and their index files, then probe every 200 ms up to 60 s
    note "before release: links=$(links) WARN=$(warn_count)"
    phase R_start
    local f; for f in $(ls "$R/cdc_raw" | grep -E '^CommitLog-[0-9]+-[0-9]+\.log$' | sort -t- -k3 -n | head -2); do
      rm -f "$R/cdc_raw/$f" "${R}/cdc_raw/${f%.log}_cdc.idx"; note "release: deleted $f"; done
    local r0 acc=0 att=0; r0=$(now)
    while [ $(( $(now) - r0 )) -lt 60000 ]; do att=$((att + 1)); if probe_cdc; then acc=1; break; fi; sleep 0.2; done
    note "release: accepted=$acc after $att probe(s), $(( $(now) - r0 )) ms; links=$(links)"
    phase R_end
  fi
  # --- stop and read
  phase end; note "end: links=$(links) $(last_row)"
  note "commit log dir: $(du -sb "$R/commitlog" | cut -f1) bytes; data: $(du -sb "$R/data" | cut -f1); free: $(df -h --output=avail "$HOME" | tail -1 | tr -d ' ')"
  kill "$DU_PID" 2> /dev/null; DU_PID=""
  kill -TERM "$SAMPLER_PID" 2> /dev/null; wait "$SAMPLER_PID" 2> /dev/null; SAMPLER_PID=""
  local p; p=$(cat cassandra.pid)
  nt stopdaemon | tail -1
  for i in $(seq 180); do kill -0 "$p" 2> /dev/null || break; sleep 1; done
  kill -0 "$p" 2> /dev/null && { note "stopdaemon did not finish: kill -9 $p"; kill -9 "$p"; sleep 2; }
  cp logs/system.log "$D/system.log"; cp logs/debug.log "$D/debug.log" 2> /dev/null || true
  grep -h 'Freed up' "$D/debug.log" 2> /dev/null | head -40 > "$D/freed-up-excerpt.txt" || true
  note "traces: created=$(grep -c '^pre ' "$D/cdc-verdict.txt" || true) forbidden=$(grep -c 'state=FORBIDDEN' "$D/cdc-verdict.txt" || true) deleteOld=$(grep -c '^deleteOld' "$D/cdc-verdict.txt" || true) rejectLines=$(grep -c '^reject ' "$D/cdc-verdict.txt" || true) WARN=$(grep -c '^WARN.*Rejecting mutation' "$D/system.log" || true) FreedUp=$(grep -c 'Freed up' "$D/debug.log" || true) ERROR=$(grep -c '^ERROR' "$D/system.log" || true)"
  note "sampler: $(cat "$D/sampler.summary")"
  git checkout -q conf/cassandra.yaml conf/cassandra-env.sh
  rm -rf "$R" cassandra.pid
  note "RESULT $label finished $(now); disk free $(df -h --output=avail "$HOME" | tail -1 | tr -d ' ')"
}

case "${1:-}" in
  all)
    mkdir -p "$L"
    for rep in 1 2; do
      for lab in nb128 nb256 b128 b256; do ( bash "$0" "$lab-r$rep" ) || echo "cell $lab-r$rep exit $?" >> "$L/failed.txt"; done
    done
    for lab in nb4096-r1 b4096-r1 plainnb128-r1; do ( bash "$0" "$lab" ) || echo "cell $lab exit $?" >> "$L/failed.txt"; done ;;
  "") echo "usage: $0 <label>|all" >&2; exit 2 ;;
  *) mkdir -p "$L"; cell "$1" ;;
esac
