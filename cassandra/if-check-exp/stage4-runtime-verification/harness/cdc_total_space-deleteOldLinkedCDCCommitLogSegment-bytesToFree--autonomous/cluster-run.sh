#!/usr/bin/env bash
# Stage 4 run 1, cluster tier: cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous, case B3.
#   cluster-run.sh <label>      one cell, end to end.  Labels:  b<cap>-r<rep> | nb<cap>-r<rep>   cap in MiB (16 128 256 512 4096)
#                                                               plainb128-r<rep> (non-CDC table, blocking) | cdcoff128-r1 (cdc_enabled false)
#                                                               chk-b160 (instrument check, not in the matrix)
#   cluster-run.sh all          the matrix and the controls in order (B3b, B3h), 2 repeats each
# One node from CLONE; every directory of the node on local disk under $R; logs under $L/<label>/.
set -Euo pipefail
C=${CLONE:-$HOME/cassandra-cdc}
HARNESS=${HARNESS:-$HOME/stage4-harness-run/cdc2}
L=${LOGDIR:-$HOME/stage4-logs/cdc2/cluster}
R=$HOME/cdcrun
BM=$C/build/lib/jars
export MAX_HEAP_SIZE=2G
D=""; SAMPLER_PID=""; DU_PID=""; STRESS_PID=""
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$D/summary.txt"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
daemon_up() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' > /dev/null; }
cleanup() {
  local rc=$?; trap - EXIT ERR
  [ -n "$STRESS_PID" ] && kill "$STRESS_PID" 2> /dev/null || true
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2> /dev/null || true
  [ -n "$DU_PID" ] && kill "$DU_PID" 2> /dev/null || true
  [ -n "$SAMPLER_PID" ] && kill -TERM "$SAMPLER_PID" 2> /dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) > /dev/null 2>&1 || true
    for _ in $(seq 60); do daemon_up || break; sleep 1; done
    daemon_up && { pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'; sleep 2; }; fi
  [ -d "$C/conf" ] && (cd "$C" && git checkout -q conf/cassandra.yaml 2> /dev/null) || true
  exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

nt() { (cd "$C" && bin/nodetool "$@" 2>&1); }
mx_get() { nt sjk mx -mg -b "$1" -f "$2" | awk 'NF{l=$0} END{n=split(l,a,/[ \t:=]+/); print a[n]}'; }
cql() { (cd "$C" && timeout 60 bin/cqlsh "$@" 2>&1); }
node_ready() { [ -s "$C/cassandra.pid" ] && [ "$(nt statusbinary)" = running ] && nt status | grep -q '^UN'; }
links() { ls "$R/cdc_raw" 2> /dev/null | grep -c -E '^CommitLog-[0-9]+-[0-9]+\.log$' || true; }
warn_count() { grep -c '^WARN.*Rejecting mutation to keyspace' "$C/logs/system.log" 2> /dev/null || true; }
freed_count() { grep -c 'Freed up' "$C/logs/debug.log" 2> /dev/null || true; }
phase() { echo "$(now),$1" >> "$D/phases.csv"; log "phase $1"; }
last_row() { tail -1 "$D/sampler.csv"; }

run_stress() {   # name profile rows rate threads
  local name=$1 prof=$2 rows=$3 rate=$4 thr=${5:-8}
  log "+ cassandra-stress user profile=$prof ops(insert=1) n=$rows no-warmup -rate threads=$thr throttle=$rate/s > $D/stress-$name.txt"
  (cd "$C" && tools/bin/cassandra-stress user profile="$HARNESS/$prof" "ops(insert=1)" n=$rows no-warmup -rate threads=$thr throttle=$rate/s -errors retries=0 ignore -node 127.0.0.1) > "$D/stress-$name.txt" 2>&1 &
  STRESS_PID=$!
  local t0; t0=$(now)
  while kill -0 "$STRESS_PID" 2> /dev/null; do
    sleep 2
    [ $(( $(now) - t0 )) -gt 420000 ] && { note "stress $name did not end in 420 s: killed"; kill "$STRESS_PID"; break; }
  done
  wait "$STRESS_PID" 2> /dev/null || true; STRESS_PID=""
  note "stress $name: $(grep -E 'Total errors|Total partitions|Op rate' "$D/stress-$name.txt" | tr -s ' ' | tr '\n' '|') ended $(now)"
}
probe_cdc() {   # one small CDC-tracked insert via cqlsh -> 0 if accepted
  local out; out=$(cql -e "INSERT INTO stage4cdc.cdc_rows (id, payload) VALUES ($((3000000000 + RANDOM)), 0xdeadbeef)") && ! echo "$out" | grep -qi -E 'error|failure|exception'
}
probe_plain() {
  local out; out=$(cql --request-timeout=5 -e "INSERT INTO stage4cdc.plain_rows (id, payload) VALUES ($((4000000000 + RANDOM)), 0xdeadbeef)") && ! echo "$out" | grep -qi -E 'error|failure|exception'
}
settle() {   # require 15 prompt non-CDC writes in a row (a bulk write through the mapped commit log can stall every logged write)
  local streak=0 t0; t0=$(now)
  while [ $(( $(now) - t0 )) -lt 240000 ] && [ "$streak" -lt 15 ]; do
    local s; s=$(now)
    if probe_plain && [ $(( $(now) - s )) -lt 4000 ]; then streak=$((streak + 1)); else streak=0; fi
    sleep 1
  done
  note "settle: streak $streak after $(( ($(now) - t0) / 1000 )) s"
}

cell() {
  local label=$1 mode cap rep kind=cdc enabled=true prof=cdc-rows-64k.yaml
  rep=${label##*-r}; local head=${label%-r*}
  case $head in
    b[0-9]*)      mode=blocking;    cap=${head#b} ;;
    nb[0-9]*)     mode=nonblocking; cap=${head#nb} ;;
    plainb[0-9]*) mode=blocking;    cap=${head#plainb}; kind=plain; prof=plain-rows-64k.yaml ;;
    cdcoff[0-9]*) mode=nonblocking; cap=${head#cdcoff}; enabled=false ;;
    chk-b[0-9]*)  mode=blocking;    cap=${head#chk-b}; rep=${label##*-r}; ;;
    *) echo "bad label $label" >&2; exit 2 ;;
  esac
  [[ "$label" == chk-* ]] && rep=1
  local rows rate
  case $cap in
    16)   rows=6144 ;;
    4096) rows=24576 ;;
    160)  rows=7680 ;;
    *)    rows=$((3 * cap * 16)) ;;
  esac
  [ "$kind" = plain ] && rows=6144; [ "$enabled" = false ] && rows=6144
  rate=$(( (rows + 119) / 120 ))
  D=$L/$label; [ -e "$D" ] && mv "$D" "$D.attempt-$(date +%s)"; mkdir -p "$D"; : > "$D/summary.txt"; : > "$D/phases.csv"
  exec > >(tee -a "$D/session.log") 2>&1
  note "== $label: mode=$mode cap=${cap}MiB cdc_enabled=$enabled table=$kind rows=$rows (=$((rows / 16)) MiB) rate=$rate/s heap=$MAX_HEAP_SIZE"
  cd "$C"
  daemon_up && fail "a CassandraDaemon is running"
  ( cd "$HARNESS" && sha256sum -c SHA256SUMS > /dev/null ) || fail "harness copy differs"
  [ "$(git describe --tags)" = cassandra-5.0.9 ] || fail "clone not at the tag"
  [ "$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)" -ge 20 ] || fail "less than 20 GB free"
  ss -ltn | grep -q -E ':(7199|9042|9091)\b' && fail "a port is busy"
  # --- config
  git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
  sed -i "s/^cdc_enabled: false\$/cdc_enabled: $enabled/" conf/cassandra.yaml
  {
    echo "cdc_total_space: ${cap}MiB"
    echo "cdc_free_space_check_interval: 250ms"
    echo "cdc_raw_directory: $R/cdc_raw"
    echo "commitlog_directory: $R/commitlog"
    echo "data_file_directories: [$R/data]"
    echo "hints_directory: $R/hints"
    echo "saved_caches_directory: $R/saved_caches"
    echo "commitlog_total_space: 1024MiB"
    echo "memtable_heap_space: 1024MiB"
    [ "$mode" = nonblocking ] && echo "cdc_block_writes: false"
  } >> conf/cassandra.yaml
  git diff -U0 conf/cassandra.yaml | grep '^[+-][^+-]' > "$D/yaml.diff"; cat "$D/yaml.diff" >&2
  # --- reset: all node data on local disk under $R
  rm -rf "$R" cassandra.pid; mkdir -p "$R"
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then mv logs "$L/logs.before-$label.$(date +%s)"; fi; mkdir -p logs
  # --- start (Byteman observation rules: creation trace, deleteOld pass, rejection)
  local opts="-Dstage4.byteman.out=$D/cdc-verdict.txt -javaagent:$BM/byteman-4.0.20.jar=script:$HARNESS/cdc-verdict.btm,listener:true"
  note "JVM_EXTRA_OPTS=$opts; ulimit -n $(ulimit -n)"
  JVM_EXTRA_OPTS="$opts" bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1
  local i=0; until node_ready; do sleep 1; i=$((i + 1)); daemon_up || fail "daemon died at start (stdout.txt)"; [ $i -ge 240 ] && fail "start timeout"; done
  note "node up after ${i}s"
  cql -e "SELECT name, value FROM system_views.settings WHERE name IN ('cdc_enabled','cdc_total_space','cdc_block_writes','commitlog_segment_size','commitlog_total_space','cdc_raw_directory','cdc_free_space_check_interval')" > "$D/settings.txt"
  sed 's/^/    | /' "$D/settings.txt" >&2
  grep -q "cdc_total_space *| *${cap}MiB\|cdc_total_space *| *${cap}$" "$D/settings.txt" || note "NOTE: cdc_total_space read-back differs from ${cap}MiB (settings.txt)"
  grep -q "commitlog_segment_size *| *32" "$D/settings.txt" || fail "segment size is not 32 MiB"
  nt setlogginglevel org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDC DEBUG > /dev/null
  # --- schema while idle
  cql -e "CREATE KEYSPACE IF NOT EXISTS stage4cdc WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}; CREATE TABLE IF NOT EXISTS stage4cdc.cdc_rows (id bigint, payload blob, PRIMARY KEY (id)) WITH cdc = true; CREATE TABLE IF NOT EXISTS stage4cdc.plain_rows (id bigint, payload blob, PRIMARY KEY (id)) WITH cdc = false;" > "$D/schema.txt" || fail "schema"
  # --- samplers: fine (50 ms, the sampler of the guided harness) and du -sb every 2 s (B3d)
  mkdir -p "$R/cdc_raw"
  python3 "$HARNESS/cdc-sampler.py" "$R/cdc_raw" "$D/sampler" 0.05 &
  SAMPLER_PID=$!
  ( while :; do echo "$(now) cdc_raw=$(du -sb "$R/cdc_raw" 2> /dev/null | cut -f1) alloc=$(du -s --block-size=1 "$R/cdc_raw" 2> /dev/null | cut -f1) commitlog=$(du -sb "$R/commitlog" 2> /dev/null | cut -f1) data=$(du -sb "$R/data" 2> /dev/null | cut -f1) free=$(df --output=avail -B1 "$HOME" | tail -1 | tr -d ' ')"; sleep 2; done ) > "$D/du.txt" 2>&1 &
  DU_PID=$!
  sleep 5; phase idle; note "idle: links=$(links) cdc_raw_exists=$([ -d "$R/cdc_raw" ] && echo yes || echo no) $(last_row)"
  # --- workload (B3c): about 3 x cap of 64 KiB CDC rows over about 2 minutes, no consumer
  phase W_start; local w0; w0=$(now)
  run_stress W "$prof" "$rows" "$rate" 8
  phase W_end
  sleep 3
  note "after workload: links=$(links) $(last_row) WARN=$(warn_count) Freed_up=$(freed_count) wall=$(( ($(now) - w0) / 1000 ))s"
  nt flush > /dev/null 2>&1 || true    # flush only at the end (B3c)
  sleep 3; note "after flush: links=$(links) $(last_row)"
  if [ "$mode" = blocking ] && [ "$kind" = cdc ] && [ "$enabled" = true ]; then
    # --- B3e step 6: a consumer deletes the two oldest links and their index files (amendment 2026-10-22); then more inserts
    if [ "$cap" -ge 64 ] && [ "$cap" -lt 4096 ]; then
      settle
      note "before release: links=$(links) listing=$(ls -l "$R/cdc_raw" | awk 'NR>1{print $9":"$5}' | tr '\n' ' ')"
      phase R_start
      local del=0 f
      for f in $(ls "$R/cdc_raw" | grep -E '^CommitLog-[0-9]+-[0-9]+\.log$' | sort -t- -k3 -n | head -2); do
        rm -f "$R/cdc_raw/$f" "$R/cdc_raw/${f%.log}_cdc.idx"; del=$((del + 1)); note "release: deleted $f"; done
      local r0 acc=0 att=0; r0=$(now)
      while [ $(( $(now) - r0 )) -lt 60000 ]; do att=$((att + 1)); if probe_cdc; then acc=1; break; fi; sleep 0.2; done
      note "release: accepted=$acc after $att probe(s), $(( $(now) - r0 )) ms; links=$(links)"
      phase R_end
      run_stress R2 "$prof" 1000 100 4          # a few more inserts (62.5 MiB)
      sleep 3; note "after more inserts: links=$(links) $(last_row) WARN=$(warn_count)"
    fi
    # --- B3e step 7: blocking -> non-blocking live through JMX, writes resume, old segments are deleted
    if [ "$cap" -lt 4096 ]; then
      if [ "$cap" -ge 64 ]; then run_stress REFILL "$prof" $((cap * 16 + 640)) 100 4; sleep 3; fi   # back to the cap
      note "before switch: links=$(links) WARN=$(warn_count) probe_cdc=$(probe_cdc && echo accepted || echo rejected) CDCBlockWrites=$(mx_get 'org.apache.cassandra.db:type=Commitlog' CDCBlockWrites)"
      local before_list; before_list=$(ls "$R/cdc_raw" | grep -E '^CommitLog-[0-9]+-[0-9]+\.log$' | sort | tr '\n' ' ')
      phase S_start
      nt sjk mx -ms -b org.apache.cassandra.db:type=Commitlog -f CDCBlockWrites -v false > "$D/jmx-set.txt" 2>&1 || true
      note "switch: CDCBlockWrites now $(mx_get 'org.apache.cassandra.db:type=Commitlog' CDCBlockWrites); jmx-set: $(tr '\n' ' ' < "$D/jmx-set.txt" | cut -c1-120)"
      local s0 acc2=0 att2=0; s0=$(now)
      while [ $(( $(now) - s0 )) -lt 60000 ]; do att2=$((att2 + 1)); if probe_cdc; then acc2=1; break; fi; sleep 0.2; done
      note "switch: first CDC probe accepted=$acc2 after $att2 probe(s), $(( $(now) - s0 )) ms"
      run_stress S2 "$prof" 3072 100 4        # 192 MiB: at least five segment creations
      phase S_end; sleep 3
      local after_list; after_list=$(ls "$R/cdc_raw" | grep -E '^CommitLog-[0-9]+-[0-9]+\.log$' | sort | tr '\n' ' ')
      note "switch: links before=[$before_list] after=[$after_list] Freed_up=$(freed_count) WARN=$(warn_count)"
    fi
  fi
  if [ "$mode" = nonblocking ] && [ "$kind" = cdc ] && [ "$enabled" = true ]; then
    note "nonblocking end: listing=$(ls -l "$R/cdc_raw" | awk 'NR>1{print $9":"$5}' | tr '\n' ' ')"
  fi
  # --- stop and read
  phase end; note "final: links=$(links) $(last_row)"
  note "final listing: $(ls -l "$R/cdc_raw" 2> /dev/null | awk 'NR>1{print $9":"$5}' | tr '\n' ' ')"
  note "commit log dir: $(du -sb "$R/commitlog" | cut -f1) bytes; data: $(du -sb "$R/data" | cut -f1); free: $(df -h --output=avail "$HOME" | tail -1 | tr -d ' ')"
  kill "$DU_PID" 2> /dev/null; DU_PID=""
  kill -TERM "$SAMPLER_PID" 2> /dev/null; wait "$SAMPLER_PID" 2> /dev/null; SAMPLER_PID=""
  nt stopdaemon | tail -1
  for i in $(seq 180); do daemon_up || break; sleep 1; done
  daemon_up && { note "stopdaemon did not finish: kill -9"; pkill -9 -f '[o]rg.apache.cassandra.service.CassandraDaemon'; sleep 2; }
  cp logs/system.log "$D/system.log"; cp logs/debug.log "$D/debug.log" 2> /dev/null || true
  grep -h 'Freed up' "$D/debug.log" 2> /dev/null | head -40 > "$D/freed-up-excerpt.txt" || true
  note "traces: created=$(grep -c '^pre ' "$D/cdc-verdict.txt" || true) forbidden=$(grep -c 'state=FORBIDDEN' "$D/cdc-verdict.txt" || true) deleteOld=$(grep -c '^deleteOld' "$D/cdc-verdict.txt" || true) rejectLines=$(grep -c '^reject ' "$D/cdc-verdict.txt" || true) WARN=$(grep -c '^WARN.*Rejecting mutation' "$D/system.log" || true) FreedUp=$(grep -c 'Freed up' "$D/debug.log" || true) ERROR=$(grep -c '^ERROR' "$D/system.log" || true)"
  note "sampler: $(cat "$D/sampler.summary")"
  rm -rf "$R"
  note "RESULT $label finished $(now); disk free $(df -h --output=avail "$HOME" | tail -1 | tr -d ' ')"
}

case "${1:-}" in
  all)
    mkdir -p "$L"
    for rep in 1 2; do
      for cap in 128 256 512 16; do for m in b nb; do ( "$0" "$m$cap-r$rep" ) || echo "cell $m$cap-r$rep exit $?" >> "$L/failed.txt"; done; done
      ( "$0" "b4096-r$rep" ) || echo "cell b4096-r$rep exit $?" >> "$L/failed.txt"
      ( "$0" "plainb128-r$rep" ) || echo "cell plainb128-r$rep exit $?" >> "$L/failed.txt"
    done
    ( "$0" "nb4096-r1" ) || echo "cell nb4096-r1 exit $?" >> "$L/failed.txt"
    ( "$0" "cdcoff128-r1" ) || echo "cell cdcoff128-r1 exit $?" >> "$L/failed.txt" ;;
  "") echo "usage: $0 <label>|all" >&2; exit 2 ;;
  *) mkdir -p "$L"; cell "$1" ;;
esac
