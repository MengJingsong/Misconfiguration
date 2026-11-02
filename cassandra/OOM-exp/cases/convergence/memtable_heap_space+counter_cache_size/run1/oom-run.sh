#!/usr/bin/env bash
# OOM-exp convergence case: memtable_heap_space + counter_cache_size, shared budget = JVM heap.
#
# Usage:
#   oom-run.sh baseline                 idle heap-after-GC with both knobs tiny/off
#   oom-run.sh arm <name> <M_MiB_or_blank> <C_MiB_or_blank> <workloads: write|counter|both>
#
# Logs every command to ~/oom-exp-logs/<name>/session.log; readings to <name>/summary.txt.
set -Eeuo pipefail

C=$HOME/cassandra-run1
L=$HOME/oom-exp-logs
XMX=${XMX:-1024M}
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
  local u; u=$(grep -oE 'region size [0-9]+K, [0-9]+ used' "$D/heap-$tag.txt" | head -1 || true)
  note "heap $tag: $(grep -E '^ *garbage-first heap' -A2 "$D/heap-$tag.txt" | tr '\n' ' ')"
}

configure_yaml() {
  local M=$1 C=$2
  runto /dev/null bash -c "cd $PWD"  # no-op to keep structure
  git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
  sed -i -e 's/^memtable_allocation_type: heap_buffers$/memtable_allocation_type: unslabbed_heap_buffers/' conf/cassandra.yaml
  if [ -n "$M" ]; then sed -i -e "s/^# memtable_heap_space: 2048MiB\$/memtable_heap_space: ${M}MiB/" conf/cassandra.yaml; fi
  sed -i -e "s/^# memtable_cleanup_threshold: 0.11\$/memtable_cleanup_threshold: 0.99/" conf/cassandra.yaml
  if [ -n "$C" ]; then sed -i -e "s/^counter_cache_size:\$/counter_cache_size: ${C}MiB/" conf/cassandra.yaml; fi
  git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  note "yaml diff: $(grep '^[+-][^+-]' "$D/cassandra.yaml.diff" | tr '\n' '|')"
}

start_node() {
  cd "$C"
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports 7000/7199/9042 free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042)\b"'
  rm -rf "$C"/data/* "$C/cassandra.pid"
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then mkdir -p "$D/prev-logs"; mv logs/* "$D/prev-logs/" 2>/dev/null || true; fi
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
  grep -E 'memtable_heap_space|Global memtable|counter cache|Initializing counter cache' "$SYSLOG" | head -10 >> "$D/startup-lines.txt" || true
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

# ------------------------------------------------------------------ baseline
cmd_baseline() {
  D=$L/baseline; start_log
  cd "$C"
  configure_yaml 32 1
  start_node
  note "baseline config: memtable_heap_space=32MiB (tiny), counter_cache_size=1MiB (tiny), -Xmx$XMX"
  sleep 5
  heap_sample idle
  stop_node
  log "BASELINE DONE"
}

# ------------------------------------------------------------------ one arm
# cmd_arm <name> <M|-> <C|-> <workload: write|counter|both>
cmd_arm() {
  local name=$1 M=$2 CC=$3 WL=$4
  [ "$M" = "-" ] && M=32   # safe tiny default when not the arm under test
  [ "$CC" = "-" ] && CC=1
  D=$L/$name; start_log "$@"
  cd "$C"
  configure_yaml "$M" "$CC"
  start_node
  note "== arm $name: M=${M}MiB C=${CC}MiB workload=$WL -Xmx=$XMX"
  heap_sample idle
  create_schema

  local WRITE_PID="" CNT_PID=""
  if [ "$WL" = "write" ] || [ "$WL" = "both" ]; then
    log "+ cassandra-stress write (background)"
    tools/bin/cassandra-stress write n=3000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256 > "$D/stress-write.txt" 2>&1 &
    WRITE_PID=$!
  fi
  if [ "$WL" = "counter" ] || [ "$WL" = "both" ]; then
    log "+ cassandra-stress counter_write (background)"
    tools/bin/cassandra-stress counter_write n=600000 no-warmup -rate threads=64 > "$D/stress-counter.txt" 2>&1 &
    CNT_PID=$!
  fi

  # sample heap periodically while workload(s) run
  local i=0 oomed=0
  for i in $(seq 1 60); do
    sleep 5
    if daemon_up; then
      jcmd "$PID" GC.heap_info > "$D/heap-sample-$i.txt" 2>&1 || true
      note "sample $i t=$(now): $(grep -E 'garbage-first heap' -A1 "$D/heap-sample-$i.txt" | tr '\n' ' ')"
    else
      note "sample $i: node process is GONE (possible OOM-kill or crash)"
      oomed=1
      break
    fi
    # stop once both requested workloads have exited
    local wdone=1
    [ -n "$WRITE_PID" ] && kill -0 "$WRITE_PID" 2>/dev/null && wdone=0
    [ -n "$CNT_PID" ] && kill -0 "$CNT_PID" 2>/dev/null && wdone=0
    [ "$wdone" = 1 ] && { note "both requested workloads finished after sample $i"; break; }
  done
  [ -n "$WRITE_PID" ] && wait "$WRITE_PID" 2>/dev/null || true
  [ -n "$CNT_PID" ] && wait "$CNT_PID" 2>/dev/null || true

  heap_sample final
  grep -c '^ERROR' "$SYSLOG" > "$D/error-count.txt" 2>&1 || echo 0 > "$D/error-count.txt"
  grep '^ERROR' "$SYSLOG" > "$D/error-lines.txt" 2>&1 || true
  grep -i 'OutOfMemoryError' "$SYSLOG" "$D"/stress-*.txt 2>/dev/null > "$D/oom-grep.txt" || true
  note "ERROR lines in system.log: $(cat "$D/error-count.txt")"
  note "OutOfMemoryError mentions: $(wc -l < "$D/oom-grep.txt" 2>/dev/null || echo 0)"
  dmesg | grep -i 'out of memory\|oom-kill\|killed process' > "$D/dmesg-oom.txt" 2>&1 || true
  note "dmesg OOM-kill lines: $(wc -l < "$D/dmesg-oom.txt")"
  if daemon_up; then note "node alive at end"; else note "node process is GONE at end"; fi

  if daemon_up; then stop_node; else note "skip stop_node: daemon already gone"; fi
  log "ARM $name DONE (oomed-during-sampling=$oomed)"
}

case "${1:-}" in
  baseline) cmd_baseline ;;
  arm) shift; cmd_arm "$@" ;;
  *) echo "usage: $0 baseline|arm <name> <M|-> <C|-> <write|counter|both>" >&2; exit 2 ;;
esac
