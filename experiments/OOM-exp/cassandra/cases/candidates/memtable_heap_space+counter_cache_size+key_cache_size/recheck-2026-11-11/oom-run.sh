#!/usr/bin/env bash
# OOM-exp convergence case: memtable_heap_space + counter_cache_size + key_cache_size,
# shared budget = JVM heap. Third constraint added to the closed M+C case.
#
# Usage:
#   oom-run.sh baseline                              idle heap-after-GC, all three knobs tiny/off
#   oom-run.sh arm <name> <M|-> <C|-> <K|-> <workloads: write,counter,read (comma list)>
#     (an arm whose workload list includes "read" preloads+flushes 500000 partitions
#      under its own node before launching the requested background workloads, since
#      key cache only engages on reads that go to an sstable, not the memtable.)
#
# Logs every command to ~/oom-exp-logs/<name>/session.log; readings to <name>/summary.txt.
#
# R4 recheck copy (2026-11-11, node apt179): paths repointed to /mydata/oom-recheck/R4, XMX pinned,
# sampling continues past sample 90 up to a 30-min cap (instead of a blind wait), nodetool-info cache
# readings every 6th sample, end-of-arm nodetool info + class histogram, node logs/heap dump kept per
# arm in <name>/node-logs, a 'validate' subcommand (modest load + diagnostic heap dump), and a
# stress-summary extract. Workloads, yaml edits and JVM options are unchanged.
set -Eeuo pipefail

C=/mydata/oom-recheck/R4/cassandra
L=/mydata/oom-recheck/R4/logs
XMX=1024M            # pinned (no env override)
MAXS=360             # sampling cap: 360 x 5 s = 30 min per arm
N_PRELOAD=500000; N_WRITE=3000000; N_COUNTER=600000; N_READ=4000000
SYSLOG=$C/logs/system.log
D=""; S=""; PID=""

log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
run()  { log "+ $*"; "$@"; local rc=$?; log "  rc=$rc"; return $rc; }
runto(){ local f=$1; shift; log "+ $* > $f"; local rc=0; "$@" > "$f" 2>&1 || rc=$?
  log "  rc=$rc ($(wc -l < "$f") lines in $f)"; return $rc; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
wait_for() { local d=$1 t=$2 i=0; shift 2
  until "$@"; do sleep 1; i=$((i+1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s waiting for: $d"; done
  log "ok: $d (after ${i}s)"; }
daemon_up() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null; }

cleanup() {
  local rc=$?; trap - EXIT ERR
  [ "$rc" -ne 0 ] && log "EXIT rc=$rc: stopping stress and node"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) >/dev/null 2>&1 || true
    for _ in $(seq 60); do daemon_up || break; sleep 1; done; fi
  if daemon_up; then log "WARNING: a CassandraDaemon is still running"; kill -9 $(pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon') 2>/dev/null || true; fi
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

start_log() { mkdir -p "$L"; if [ -e "$D" ] && [ -n "$(ls -A "$D" 2>/dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  log "script: $0 $*"; log "host: $(hostname)"; }

heap_sample() { local tag=$1
  runto "$D/gc-run-$tag.txt" jcmd "$PID" GC.run
  runto "$D/heap-$tag.txt" jcmd "$PID" GC.heap_info
  note "heap $tag: $(grep -E '^ *garbage-first heap' -A2 "$D/heap-$tag.txt" | tr '\n' ' ')"
}

configure_yaml() {
  local M=$1 C=$2 K=$3
  git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
  sed -i -e 's/^memtable_allocation_type: heap_buffers$/memtable_allocation_type: unslabbed_heap_buffers/' conf/cassandra.yaml
  if [ -n "$M" ]; then sed -i -e "s/^# memtable_heap_space: 2048MiB\$/memtable_heap_space: ${M}MiB/" conf/cassandra.yaml; fi
  sed -i -e "s/^# memtable_cleanup_threshold: 0.11\$/memtable_cleanup_threshold: 0.99/" conf/cassandra.yaml
  if [ -n "$C" ]; then sed -i -e "s/^counter_cache_size:\$/counter_cache_size: ${C}MiB/" conf/cassandra.yaml; fi
  if [ -n "$K" ]; then sed -i -e "s/^key_cache_size:\$/key_cache_size: ${K}MiB/" conf/cassandra.yaml; fi
  git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  note "yaml diff: $(grep '^[+-][^+-]' "$D/cassandra.yaml.diff" | tr '\n' '|')"
}

start_node() {
  cd "$C"
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports 7000/7199/9042 free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042)\b"'
  rm -rf "$C"/data/* "$C/cassandra.pid"
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then mkdir -p "$D/prev-logs"; mv logs/* "$D/prev-logs/" 2>/dev/null || true; fi
  rm -rf "$C"/saved_caches/* 2>/dev/null || true
  mkdir -p logs
  export MAX_HEAP_SIZE=$XMX; unset HEAP_NEWSIZE || true
  log "+ bin/cassandra -p cassandra.pid > $D/stdout.txt 2>&1"
  bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1
  node_ready() { [ -s cassandra.pid ] || return 1
    kill -0 "$(cat cassandra.pid)" 2>/dev/null || fail "node died during startup (see $D/stdout.txt)"
    grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; }
  wait_for "node listening for CQL clients" 300 node_ready
  unset MAX_HEAP_SIZE
  PID=$(cat cassandra.pid); note "node pid $PID"
  ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"
  check "JVM has -Xmx$XMX" grep -qx -- "-Xmx$XMX" "$D/jvm-args.txt"
  grep -E 'memtable_heap_space|Global memtable|counter cache|Initializing counter cache|key cache|Initializing key cache' "$SYSLOG" | head -10 >> "$D/startup-lines.txt" || true
  note "startup lines: $(cat "$D/startup-lines.txt" | tr '\n' '|')"
}

stop_node() {
  cd "$C"
  bin/nodetool drain >/dev/null 2>&1 || true
  sleep 1
  bin/nodetool stopdaemon >/dev/null 2>&1 || true
  for _ in $(seq 60); do daemon_up || break; sleep 1; done
  if daemon_up; then kill -9 "$PID" 2>/dev/null || true; sleep 1; fi
  check "no CassandraDaemon left" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
}

create_schema() {
  cd "$C"
  bin/cqlsh -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1} AND durable_writes = false;" 2>&1 | tee "$D/create-ks.txt" || true
}

# --------------------------------------------------------------- baseline
cmd_baseline() {
  D=$L/baseline3; start_log
  cd "$C"
  configure_yaml 32 1 1
  start_node
  note "baseline config: memtable_heap_space=32MiB, counter_cache_size=1MiB, key_cache_size=1MiB (all tiny), -Xmx$XMX"
  sleep 5
  heap_sample idle
  stop_node
  log "BASELINE3 DONE"
}

# --------------------------------------------------------------- one arm
# cmd_arm <name> <M|-> <C|-> <K|-> <workloads: comma list of write,counter,read>
cmd_arm() {
  local name=$1 M=$2 CC=$3 K=$4 WL=$5
  [ "$M" = "-" ] && M=32
  [ "$CC" = "-" ] && CC=1
  [ "$K" = "-" ] && K=1
  D=$L/$name; start_log "$@"
  cd "$C"
  configure_yaml "$M" "$CC" "$K"
  start_node
  note "== arm $name: M=${M}MiB C=${CC}MiB K=${K}MiB workloads=$WL -Xmx=$XMX"
  heap_sample idle
  create_schema

  # the 'read' workload needs an on-disk (flushed) dataset so key cache actually
  # engages (it caches sstable partition positions, not memtable rows) — preload
  # and flush under THIS arm's own already-running node, then re-sample idle heap.
  if [[ ",$WL," == *,read,* ]]; then
    log "+ cassandra-stress write (preload, 500000 partitions, quiet, for the read arm's dataset)"
    tools/bin/cassandra-stress write n=$N_PRELOAD no-warmup -col 'size=FIXED(1024)' -rate threads=64 > "$D/stress-preload.txt" 2>&1
    bin/nodetool flush
    note "preload done: $N_PRELOAD partitions written and flushed to sstable"
    heap_sample after-preload
  fi

  local WRITE_PID="" CNT_PID="" READ_PID=""
  if [[ ",$WL," == *,write,* ]]; then
    log "+ cassandra-stress write (background)"
    tools/bin/cassandra-stress write n=$N_WRITE no-warmup -col 'size=FIXED(1024)' -rate threads=256 > "$D/stress-write.txt" 2>&1 &
    WRITE_PID=$!
  fi
  if [[ ",$WL," == *,counter,* ]]; then
    log "+ cassandra-stress counter_write (background)"
    tools/bin/cassandra-stress counter_write n=$N_COUNTER no-warmup -rate threads=64 > "$D/stress-counter.txt" 2>&1 &
    CNT_PID=$!
  fi
  if [[ ",$WL," == *,read,* ]]; then
    log "+ cassandra-stress read (background, against preloaded 500000 partitions)"
    tools/bin/cassandra-stress read n=$N_READ no-warmup -col 'size=FIXED(1024)' -pop "seq=1..$N_PRELOAD" -rate threads=192 > "$D/stress-read.txt" 2>&1 &
    READ_PID=$!
  fi

  local i=0 oomed=0 capped=1
  note "workloads launched t=$(now)"
  for i in $(seq 1 $MAXS); do
    sleep 5
    if daemon_up; then
      jcmd "$PID" GC.heap_info > "$D/heap-sample-$i.txt" 2>&1 || true
      note "sample $i t=$(now): $(grep -E 'garbage-first heap' -A1 "$D/heap-sample-$i.txt" | tr '\n' ' ')"
      if [ $((i % 6)) = 0 ]; then
        (cd "$C" && timeout 60 bin/nodetool info 2>&1 | grep -E 'Cache' | tr -s ' ' | tr '\n' '|') > "$D/ninfo-$i.txt" 2>&1 || true
        note "nodetool-info $i t=$(now): $(cat "$D/ninfo-$i.txt")"
      fi
    else
      note "sample $i t=$(now): node process is GONE (possible OOM-kill or crash)"
      oomed=1; capped=0
      log "node gone: stopping stress clients"
      pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
      break
    fi
    local wdone=1
    [ -n "$WRITE_PID" ] && kill -0 "$WRITE_PID" 2>/dev/null && wdone=0
    [ -n "$CNT_PID" ] && kill -0 "$CNT_PID" 2>/dev/null && wdone=0
    [ -n "$READ_PID" ] && kill -0 "$READ_PID" 2>/dev/null && wdone=0
    [ "$wdone" = 1 ] && { note "all requested workloads finished after sample $i t=$(now)"; capped=0; break; }
  done
  if [ "$capped" = 1 ]; then note "sampling cap ($MAXS samples) reached with workloads still running: stopping stress"; pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true; fi
  [ -n "$WRITE_PID" ] && wait "$WRITE_PID" 2>/dev/null || true
  [ -n "$CNT_PID" ] && wait "$CNT_PID" 2>/dev/null || true
  [ -n "$READ_PID" ] && wait "$READ_PID" 2>/dev/null || true

  if daemon_up; then heap_sample final || note "final heap sample failed (node died?)"; fi
  if daemon_up; then
    (cd "$C" && timeout 120 bin/nodetool info > "$D/nodetool-info-final.txt" 2>&1) || true
    note "nodetool-info final: $(grep -E 'Cache' "$D/nodetool-info-final.txt" | tr -s ' ' | tr '\n' '|')"
    runto "$D/class-histogram-final.txt" jcmd "$PID" GC.class_histogram || true
  fi
  for f in "$D"/stress-*.txt; do
    note "stress $(basename "$f"): $(grep -E '^(Op rate|Partition rate|Total partitions|Total errors|Total operation time)' "$f" | tr -s ' ' | tr '\n' '|') last: $(tail -2 "$f" | tr '\n' '|' | cut -c1-200)"
  done
  grep -c '^ERROR' "$SYSLOG" > "$D/error-count.txt" 2>&1 || echo 0 > "$D/error-count.txt"
  grep '^ERROR' "$SYSLOG" > "$D/error-lines.txt" 2>&1 || true
  grep -i 'OutOfMemoryError' "$SYSLOG" "$D"/stress-*.txt 2>/dev/null > "$D/oom-grep.txt" || true
  note "ERROR lines in system.log: $(cat "$D/error-count.txt")"
  note "OutOfMemoryError mentions: $(wc -l < "$D/oom-grep.txt" 2>/dev/null || echo 0)"
  sudo dmesg -T 2>/dev/null | grep -i 'out of memory\|oom-kill\|killed process' > "$D/dmesg-oom.txt" 2>&1 || true
  note "dmesg OOM-kill lines: $(wc -l < "$D/dmesg-oom.txt")"
  if daemon_up; then note "node alive at end"; else note "node process is GONE at end"; fi

  if [ -n "${DIAG_DUMP:-}" ] && daemon_up; then runto "$D/heap-dump-cmd.txt" jcmd "$PID" GC.heap_dump "$D/diag-$name.hprof" || true; fi
  if daemon_up; then stop_node; else note "skip stop_node: daemon already gone"; fi
  sleep 2; mkdir -p "$D/node-logs"; mv "$C"/logs/* "$D/node-logs/" 2>/dev/null || true
  note "node-logs: $(ls "$D/node-logs" | tr '\n' ' ')"
  log "ARM $name DONE (oomed-during-sampling=$oomed)"
}

# modest-load validation: filed capacities (350/250/200), all three workloads at ~1/10-1/20 of
# the filed n, plus a diagnostic heap dump at the end to test the hprof parser (U vs K per domain).
cmd_validate() {
  N_PRELOAD=50000; N_WRITE=150000; N_COUNTER=60000; N_READ=300000; DIAG_DUMP=1
  cmd_arm validate 350 250 200 write,counter,read
}

case "${1:-}" in
  baseline) cmd_baseline ;;
  arm) shift; cmd_arm "$@" ;;
  validate) cmd_validate ;;
  *) echo "usage: $0 baseline|arm <name> <M|-> <C|-> <K|-> <write,counter,read comma-list>" >&2; exit 2 ;;
esac
