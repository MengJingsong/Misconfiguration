#!/usr/bin/env bash
# OOM-exp convergence run 4: row_cache_size + index_summary_capacity,
# shared budget = off-heap/direct memory. Unparks the off-heap group.
#
# The real ceiling for this group is a cgroup memory limit, not
# -XX:MaxDirectMemorySize: both row_cache_size (SerializingCache) and
# index_summary_capacity allocate through MemoryUtil.allocate -> JNA
# Native.malloc (plain libc malloc), which never touches the JVM's
# DirectByteBuffer/Bits.reserveMemory accounting that -XX:MaxDirectMemorySize
# polices. So MaxDirectMemorySize is set (as instructed) but is not the
# enforcement point; the actual budget enforced here is a cgroup v2
# memory.max on the whole JVM process (heap + native malloc + everything),
# via `systemd-run --user --scope -p MemoryMax=...`.
#
# Usage:
#   oom-run.sh baseline <budget_MiB>
#   oom-run.sh arm <name> <budget_MiB> <R|-> <I|-> <workloads: row,rebuild (comma list)>
#     R = row_cache_size (MiB), I = index_summary_capacity (MiB)
#     "row" workload: preload+flush N partitions, then read them all back
#       repeatedly so row cache fills (caching ALL rows_per_partition).
#     "rebuild" workload: preload+flush N2 partitions into table isc.t
#       (min_index_interval=1, max_index_interval=128) so raw full-level
#       index summaries vastly exceed the configured capacity, then wait
#       for the 1-minute resize task to downsample them to the cap.
#
# Logs every command to ~/oom-offheap-run5/logs/<name>/session.log.
set -Eeuo pipefail

C=$HOME/cassandra-run1
L=$HOME/oom-offheap-run5/logs
XMX=${XMX:-384M}
SYSLOG=$C/logs/system.log
D=""; S=""; PID=""; UNIT=""

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
  if [ -n "$UNIT" ]; then systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; fi
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

start_log() { mkdir -p "$L"; if [ -e "$D" ] && [ -n "$(ls -A "$D" 2>/dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  log "script: $0 $*"; log "host: $(hostname)"; }

rss_sample() { local tag=$1
  if [ -r "/proc/$PID/status" ]; then
    grep -E '^(VmRSS|RssAnon|RssFile|RssShmem|VmHWM):' "/proc/$PID/status" > "$D/rss-$tag.txt" || true
    note "rss $tag: $(tr '\n' ' ' < "$D/rss-$tag.txt")"
  else
    note "rss $tag: process gone"
  fi
  if [ -n "$UNIT" ]; then
    local cg
    cg=$(find "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service" -maxdepth 3 -type d -name "$UNIT.scope" 2>/dev/null | head -1)
    if [ -n "$cg" ] && [ -r "$cg/memory.current" ]; then
      echo "memory.current=$(cat "$cg/memory.current") memory.max=$(cat "$cg/memory.max") memory.events=$(tr '\n' ' ' < "$cg/memory.events")" > "$D/cgroup-$tag.txt"
      note "cgroup $tag: $(cat "$D/cgroup-$tag.txt")"
    fi
  fi
}

configure_yaml() {
  local R=$1 I=$2
  git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
  # Stabilizer (not a studied constraint): default memtable_heap_space is
  # null -> 1/4 of -Xmx (96MiB at -Xmx384M here), which is tiny and caused
  # continuous ~32MiB flushes + tiny compactions throughout the preload
  # writes, churning disk/CPU badly enough to make writes/reads very slow
  # under this cgroup's memory pressure. Fix it to a comfortable constant so
  # the run completes in reasonable time; this is an environment knob, not
  # one of the two constraints under test.
  sed -i -e "s/^# memtable_heap_space: 2048MiB\$/memtable_heap_space: 220MiB/" conf/cassandra.yaml
  if [ -n "$R" ]; then
    sed -i -e 's/^# row_cache_class_name: org.apache.cassandra.cache.OHCProvider$/row_cache_class_name: org.apache.cassandra.cache.SerializingCacheProvider/' conf/cassandra.yaml
    sed -i -e "s/^row_cache_size: 0MiB\$/row_cache_size: ${R}MiB/" conf/cassandra.yaml
  fi
  if [ -n "$I" ]; then
    sed -i -e "s/^index_summary_capacity:\$/index_summary_capacity: ${I}MiB/" conf/cassandra.yaml
    sed -i -e "s/^index_summary_resize_interval: 60m\$/index_summary_resize_interval: ${RESIZE:-1m}/" conf/cassandra.yaml
  fi
  git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  note "yaml diff: $(grep '^[+-][^+-]' "$D/cassandra.yaml.diff" | tr '\n' '|')"
}

start_node() {
  local budget=$1
  cd "$C"
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports 7000/7199/9042 free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042)\b"'
  rm -rf "$C"/data/*
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then mkdir -p "$D/prev-logs"; mv logs/* "$D/prev-logs/" 2>/dev/null || true; fi
  mkdir -p logs
  export MAX_HEAP_SIZE=$XMX; unset HEAP_NEWSIZE || true
  export JVM_EXTRA_OPTS="-XX:MaxDirectMemorySize=${budget}M"
  UNIT="oom-offheap5-$(date +%s%N)"
  # -f (foreground) is required so the JVM is the systemd scope's own main process
  # (not forked outside it) — but note bin/cassandra's foreground branch never
  # writes a pidfile (only the backgrounding branch does; CassandraDaemon itself
  # only registers deleteOnExit on cassandra-pidfile, never creates it). So PID
  # detection below is by pgrep, not by reading a pidfile.
  log "+ systemd-run --user --scope -p MemoryMax=${budget}M -p MemorySwapMax=0 --unit=$UNIT -- bin/cassandra -f > $D/stdout.txt 2>&1 &"
  systemd-run --user --scope -p MemoryMax="${budget}M" -p MemorySwapMax=0 --unit="$UNIT" -- \
    bin/cassandra -f > "$D/stdout.txt" 2>&1 &
  local SCOPE_SHELL_PID=$!
  node_ready() {
    daemon_up || { kill -0 "$SCOPE_SHELL_PID" 2>/dev/null || fail "node died during startup (see $D/stdout.txt)"; return 1; }
    grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; }
  wait_for "node listening for CQL clients" 300 node_ready
  unset MAX_HEAP_SIZE JVM_EXTRA_OPTS
  PID=$(pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' | head -1); note "node pid $PID, systemd scope unit $UNIT, cgroup budget ${budget}MiB"
  ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"
  check "JVM has -Xmx$XMX" grep -qx -- "-Xmx$XMX" "$D/jvm-args.txt"
  check "JVM has -XX:MaxDirectMemorySize" grep -q -- "MaxDirectMemorySize=${budget}M" "$D/jvm-args.txt"
  grep -E 'Initializing row cache|Initializing index summary manager|row_cache|index summary' "$SYSLOG" | head -10 > "$D/startup-lines.txt" || true
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
  if [ -n "$UNIT" ]; then systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; UNIT=""; fi
}

create_schema() {
  # keyspace1/standard1 (row-cache workload) is created by cassandra-stress
  # 'write' itself on first use, with default caching (keys only). After that
  # first write+flush, enable_row_caching() below ALTERs it to cache
  # rows_per_partition=ALL before any reads run, so the row cache actually
  # engages. isc.t (index-summary workload) is created by the cassandra-stress
  # user profile itself (isc-profile.yaml's table_definition).
  :
}

enable_row_caching() {
  cd "$C"
  bin/cqlsh -e "ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'NONE','rows_per_partition':'ALL'};" 2>&1 | tee "$D/alter-caching.txt" || true
}

wait_resize() {
  # waits for a 'Completed resizing of index summaries' line that appears
  # AFTER $2 lines already existed in $SYSLOG (so we don't match a near-empty
  # resize that ran before the isc.t preload finished loading data).
  local tag=$1 offset=$2
  log "waiting up to 150s for an index-summary resize after system.log line $offset (1m interval)"
  local i=0
  until tail -n "+$((offset+1))" "$SYSLOG" 2>/dev/null | grep -q 'Completed resizing of index summaries'; do
    sleep 5; i=$((i+5))
    [ "$i" -ge 150 ] && { note "WARNING: resize did not complete within 150s"; break; }
  done
  tail -n "+$((offset+1))" "$SYSLOG" | grep -B1 'Completed resizing of index summaries\|Redistributing index summaries\|downsample:' > "$D/resize-$tag.txt" || true
  note "resize $tag: $(grep 'Completed resizing' "$D/resize-$tag.txt" | tail -1)"
}

cache_info() { local tag=$1
  (cd "$C" && bin/nodetool info) > "$D/nodetool-info-$tag.txt" 2>&1 || true
  note "cacheinfo $tag: $(grep -A1 'Cache' "$D/nodetool-info-$tag.txt" | tr '\n' '|')"
}

# --------------------------------------------------------------- baseline
cmd_baseline() {
  local budget=$1
  D=$L/baseline; start_log "$@"
  cd "$C"
  configure_yaml 1 1
  start_node "$budget"
  note "baseline config: row_cache_size=1MiB, index_summary_capacity=1MiB (tiny/off), -Xmx$XMX, cgroup budget=${budget}MiB"
  sleep 8
  rss_sample idle
  stop_node
  log "BASELINE DONE"
}

# --------------------------------------------------------------- one arm
# cmd_arm <name> <budget_MiB> <R|-> <I|-> <workloads: row,rebuild comma list> <N_row> <N_isc>
cmd_arm() {
  local name=$1 budget=$2 R=$3 I=$4 WL=$5 N_row=${6:-500000} N_isc=${7:-1200000}
  [ "$R" = "-" ] && R=1
  [ "$I" = "-" ] && I=1
  D=$L/$name; start_log "$@"
  cd "$C"
  configure_yaml "$R" "$I"
  start_node "$budget"
  note "== arm $name: R=${R}MiB I=${I}MiB workloads=$WL budget=${budget}MiB N_row=$N_row N_isc=$N_isc"
  rss_sample idle
  create_schema
  if [[ ",$WL," == *,conc,* ]]; then
    # retry-A fix: create isc.t on the idle node, before any load. In the concurrent arms the
    # stress client's own CREATE TABLE timed out (12 s driver timeout) and it wrote 0 partitions.
    bin/cqlsh --request-timeout=120 -e "CREATE KEYSPACE IF NOT EXISTS isc WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1} AND durable_writes = false; CREATE TABLE IF NOT EXISTS isc.t (k text, v blob, PRIMARY KEY (k)) WITH min_index_interval=1 AND max_index_interval=128 AND caching = {'keys':'NONE', 'rows_per_partition':'NONE'} AND compaction = {'class':'SizeTieredCompactionStrategy'};" > "$D/precreate-isc.txt" 2>&1 || note "precreate rc=$?"
    bin/cqlsh -e "DESCRIBE TABLE isc.t" > "$D/describe-isc.txt" 2>&1 && note "isc.t pre-created on idle node" || fail "isc.t pre-create failed"
  fi

  if [[ ",$WL," == *,row,* ]]; then
    log "+ cassandra-stress write (preload row-cache dataset, $N_row partitions)"
    tools/bin/cassandra-stress write n=$N_row no-warmup -col 'size=FIXED(1024)' -rate threads=64 > "$D/stress-preload-row.txt" 2>&1
    enable_row_caching
    bin/nodetool flush
    note "row preload done: $N_row partitions written, caching set to rows_per_partition=ALL, flushed"
    rss_sample after-row-preload
  fi
  local RESIZE_OFFSET=0
  local ISC_PID=""
  if [[ ",$WL," == *,after,* ]]; then
    log "+ cassandra-stress read (FOREGROUND, fill the row cache to its cap before the burst, $N_row partitions)"
    tools/bin/cassandra-stress read n=$N_row no-warmup -col 'size=FIXED(1024)' -pop "seq=1..$N_row" -rate threads=48 > "$D/stress-read-row.txt" 2>&1 || note "row read pass rc=$?"
    rss_sample after-row-fill; cache_info after-row-fill
  fi
  if [[ ",$WL," == *,conc,* ]]; then
    # run 5: NO sequential isc preload; isc write burst runs concurrently with the row read pass
    RESIZE_OFFSET=$(wc -l < "$SYSLOG")
    log "+ cassandra-stress user-table write into isc.t (BACKGROUND, concurrent with row reads, $N_isc partitions)"
    tools/bin/cassandra-stress user profile=$HOME/oom-offheap-run5/isc-profile.yaml ops\(insert=1\) n=$N_isc no-warmup -errors retries=${ISC_RETRIES:-9} -rate threads=${ISC_THREADS:-64} > "$D/stress-conc-isc.txt" 2>&1 &
    ISC_PID=$!
  fi
  if [[ ",$WL," == *,rebuild,* ]]; then
    RESIZE_OFFSET=$(wc -l < "$SYSLOG")
    log "+ cassandra-stress user-table write into isc.t (preload index-summary dataset, $N_isc partitions)"
    tools/bin/cassandra-stress user profile=$HOME/oom-offheap-run5/isc-profile.yaml ops\(insert=1\) n=$N_isc no-warmup -rate threads=64 > "$D/stress-preload-isc.txt" 2>&1
    bin/nodetool flush isc t
    note "isc preload done: $N_isc partitions written and flushed to isc.t (system.log offset $RESIZE_OFFSET)"
    rss_sample after-isc-preload
  fi

  local ROW_PID="" ISC_WAIT_DONE=0
  if [[ ",$WL," == *,row,* ]] && [[ ",$WL," != *,after,* ]]; then
    log "+ cassandra-stress read (background, one pass to fill the row cache, against $N_row partitions)"
    tools/bin/cassandra-stress read n=$N_row no-warmup -col 'size=FIXED(1024)' -pop "seq=1..$N_row" -rate threads=48 > "$D/stress-read-row.txt" 2>&1 &
    ROW_PID=$!
  fi
  if [[ ",$WL," == *,rebuild,* ]]; then
    # the resize task is scheduled on a fixed 1-minute delay from the manager's own
    # startup; sample RSS while waiting for it rather than blocking on it alone,
    # so the row-cache workload (if present) runs concurrently in the same window.
    (wait_resize "$name" "$RESIZE_OFFSET" ) &
    WAIT_PID=$!
  fi

  local i=0
  for i in $(seq 1 ${MAXSAMPLES:-120}); do
    sleep 5
    if daemon_up; then
      rss_sample "t$i"
    else
      note "sample $i: node process is GONE (possible OOM-kill or crash)"
      break
    fi
    local wdone=1
    [ -n "$ISC_PID" ] && kill -0 "$ISC_PID" 2>/dev/null && wdone=0
    [ -n "$ROW_PID" ] && kill -0 "$ROW_PID" 2>/dev/null && wdone=0
    if [[ ",$WL," == *,rebuild,* ]] && [ "$ISC_WAIT_DONE" = 0 ]; then
      if ! kill -0 "$WAIT_PID" 2>/dev/null; then ISC_WAIT_DONE=1; fi
      [ "$ISC_WAIT_DONE" = 0 ] && wdone=0
    fi
    [ "$wdone" = 1 ] && { note "all requested workloads finished after sample $i"; break; }
  done
  if [ -n "$ISC_PID" ] && daemon_up; then bin/nodetool flush isc t >/dev/null 2>&1 || true
    for h in 1 2 3 4 5 6; do sleep 5; daemon_up && rss_sample "hold$h" || { note "node GONE during hold"; break; }; done; fi
  [ -n "$ROW_PID" ] && wait "$ROW_PID" 2>/dev/null || true
  [ -n "${WAIT_PID:-}" ] && wait "$WAIT_PID" 2>/dev/null || true

  if daemon_up; then rss_sample final; cache_info final
    (cd "$C" && { bin/nodetool tablestats isc.t; bin/nodetool tablestats keyspace1.standard1; }) > "$D/tablestats-final.txt" 2>&1 || true
    note "tablestats final: $(grep -E 'Table:|Number of partitions|Index summary off heap|SSTable count' "$D/tablestats-final.txt" | tr -s ' ' | tr '\n' '|')"; fi
  grep -c '^ERROR' "$SYSLOG" > "$D/error-count.txt" 2>&1 || echo 0 > "$D/error-count.txt"
  grep '^ERROR' "$SYSLOG" > "$D/error-lines.txt" 2>&1 || true
  grep -i 'OutOfMemoryError' "$SYSLOG" "$D"/stress-*.txt 2>/dev/null > "$D/oom-grep.txt" || true
  note "ERROR lines in system.log: $(cat "$D/error-count.txt")"
  note "OutOfMemoryError mentions: $(wc -l < "$D/oom-grep.txt" 2>/dev/null || echo 0)"
  sudo dmesg -T 2>/dev/null | grep -i 'out of memory\|oom-kill\|killed process' > "$D/dmesg-oom.txt" 2>&1 || true
  note "dmesg OOM-kill lines: $(wc -l < "$D/dmesg-oom.txt")"
  if [ -n "$UNIT" ]; then
    journalctl --user -u "$UNIT" --no-pager 2>/dev/null > "$D/journal-unit.txt" || true
    grep -i 'oom\|killed' "$D/journal-unit.txt" > "$D/journal-oom-grep.txt" || true
    note "systemd scope journal OOM mentions: $(wc -l < "$D/journal-oom-grep.txt" 2>/dev/null || echo 0)"
  fi
  if daemon_up; then note "node alive at end"; else note "node process is GONE at end"; fi

  if daemon_up; then stop_node; else note "skip stop_node: daemon already gone"; [ -n "$UNIT" ] && systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; fi
  log "ARM $name DONE"
}

case "${1:-}" in
  baseline) shift; cmd_baseline "$@" ;;
  arm) shift; cmd_arm "$@" ;;
  *) echo "usage: $0 baseline <budget_MiB> | arm <name> <budget_MiB> <R|-> <I|-> <row,rebuild comma-list> [N_row] [N_isc]" >&2; exit 2 ;;
esac
