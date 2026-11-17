#!/usr/bin/env bash
# OOM-exp R1-V (2026-11-12, apt149): memtable_offheap_space + file_cache_size at their shipped, heap-derived
# defaults, under a container (cgroup v2 memory.max) budget. Derived from the R1 recheck harness
# (../memtable_offheap_space+file_cache_size/recheck-2026-11-11/harness/oom-run.sh); changes:
#   - paths /mydata/r1v; scope prefix oom-r1v-
#   - yaml: ONLY memtable_allocation_type: offheap_objects and file_cache_enabled: true (both documented values);
#     memtable_offheap_space / file_cache_size / memtable_heap_space / memtable_cleanup_threshold left UNSET
#     (defaults) unless an intervention arm passes an explicit value; F=off keeps the chunk cache disabled.
#   - heap and MaxDirectMemorySize passed explicitly as cassandra-env.sh would resolve them for a node with RAM = L
#     (heap = L/2, direct = L/4; the host has 16 GiB so the script's own `free -m` would not see L)
#   - resolved defaults read back from system.log at startup and checked against the expected values
#   - cache fill reads N_FILL partitions (enough to fill a <= 512 MiB chunk cache), not the whole dataset
# Usage: oom-run.sh arm <name> <L_MiB> <H_MiB> <M_MiB|def> <F_MiB|def|off> <workloads: preload,cachefill,memburst>
set -Eeuo pipefail
R=/mydata/r1v; C=$R/cassandra; L=${LOGDIR:-$R/logs}; SYSLOG=$C/logs/system.log
POLL_MS=${POLL_MS:-2000}; NMT=${NMT:-summary}; POLLER_PID=""; NMTLOOP_PID=""
N_DATA=${N_DATA:-800000}      # read dataset partitions (5 x 1 KiB cols ~ 5 KiB each), as in R1
N_FILL=${N_FILL:-300000}      # partitions read by the cache-fill pass (random tokens -> far more than 512 MiB of chunks)
N_BURST=${N_BURST:-2000000}   # memtable write-burst partitions, as in R1
BURST_SECS=${BURST_SECS:-240} # cap on the write burst, as in R1
D=""; S=""; PID=""; UNIT=""
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
wait_for() { local d=$1 t=$2 i=0; shift 2; until "$@"; do sleep 1; i=$((i+1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s: $d"; done; log "ok: $d (${i}s)"; }
daemon_up() { pgrep -f '^(/usr/bin/)?java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon' >/dev/null; }
cleanup() { local rc=$?; trap - EXIT ERR
  [ -n "$NMTLOOP_PID" ] && kill "$NMTLOOP_PID" 2>/dev/null || true; [ -n "$POLLER_PID" ] && kill "$POLLER_PID" 2>/dev/null || true
  pkill -f '^(/usr/bin/)?java .*org[.]apache[.]cassandra[.]stress[.]Stress' 2>/dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) >/dev/null 2>&1 || true; for _ in $(seq 60); do daemon_up || break; sleep 1; done; fi
  daemon_up && kill -9 $(pgrep -f '^(/usr/bin/)?java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon') 2>/dev/null || true
  [ -n "$UNIT" ] && systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; exit "$rc"; }
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR; trap cleanup EXIT
start_log() { mkdir -p "$L"; [ -e "$D" ] && mv "$D" "$D.attempt-$(date +%s)"; mkdir -p "$D"; S=$D/summary.txt
  exec > >(tee -a "$D/session.log") 2>&1; log "script: $0 $*"; }
cgdir() { find "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service" -maxdepth 3 -type d -name "$UNIT.scope" 2>/dev/null | head -1; }
sample() { local tag=$1
  if [ -r "/proc/$PID/status" ]; then grep -E '^(VmHWM|VmRSS|RssAnon|RssFile):' "/proc/$PID/status" > "$D/rss-$tag.txt" || true
    note "rss $tag: $(tr -s '\t ' ' ' < "$D/rss-$tag.txt" | tr '\n' ' ')"; else note "rss $tag: process gone"; fi
  local cg; cg=$(cgdir); [ -n "$cg" ] && note "cgroup $tag: cur=$(cat $cg/memory.current) $(grep -E '^(max|oom|oom_kill) ' $cg/memory.events | tr '\n' ' ')" || true; }
stats() { local tag=$1
  (cd "$C"; bin/nodetool info > "$D/info-$tag.txt" 2>&1 || true
   for t in memks.standard1 dataks.standard1; do bin/nodetool tablestats $t 2>/dev/null; done > "$D/tablestats-$tag.txt" || true)
  note "chunkcache $tag: $(grep 'Chunk Cache' "$D/info-$tag.txt" | tr -s ' ')"
  note "tablestats $tag: $(grep -E 'Table:|Memtable off heap memory used|Memtable data size|Number of partitions' "$D/tablestats-$tag.txt" | tr -s ' \t' ' ' | tr '\n' '|')"; }
configure_yaml() { local M=$1 F=$2
  git -C "$C" show HEAD:conf/cassandra.yaml > "$C/conf/cassandra.yaml"; local Y=$C/conf/cassandra.yaml
  sed -i -e "s/^memtable_allocation_type: heap_buffers\$/memtable_allocation_type: offheap_objects/" "$Y"
  [ "$F" != off ] && sed -i -e "s/^# file_cache_enabled: false\$/file_cache_enabled: true/" "$Y"
  [ "$M" != def ] && sed -i -e "s/^# memtable_offheap_space: 2048MiB\$/memtable_offheap_space: ${M}MiB/" "$Y"
  [ "$F" != def ] && [ "$F" != off ] && sed -i -e "s/^# file_cache_size: 512MiB\$/file_cache_size: ${F}MiB/" "$Y"
  git -C "$C" diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  grep -qx "memtable_allocation_type: offheap_objects" "$Y" || fail "yaml edit missing: offheap_objects"
  if [ "$F" = off ]; then grep -q '^file_cache_enabled' "$Y" && fail "file cache should stay at default (off)"; else grep -qx "file_cache_enabled: true" "$Y" || fail "yaml edit missing: file_cache_enabled"; fi
  [ "$M" = def ] && { grep -qE '^memtable_offheap_space' "$Y" && fail "memtable_offheap_space must be unset"; } || true
  [ "$F" = def ] && { grep -qE '^file_cache_size' "$Y" && fail "file_cache_size must be unset"; } || true
  grep -qE '^(memtable_heap_space|memtable_cleanup_threshold|memtable_flush_writers|networking_cache_size)' "$Y" && fail "unexpected memtable/pool key set" || true
  note "yaml: offheap_objects; file cache $([ "$F" = off ] && echo off || echo on); memtable_offheap_space=$M file_cache_size=$F (def = unset, heap-derived); diff lines: $(grep -c '^[-+][^-+]' "$D/cassandra.yaml.diff")"; }
start_node() { local budget=$1 heap=$2 direct=$3 M=$4 F=$5; cd "$C"
  check "no daemon" bash -c '! pgrep -f "^(/usr/bin/)?java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon" >/dev/null'
  check "ports free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042)\b"'
  rm -rf "$C"/data/*; [ -n "$(ls -A logs 2>/dev/null)" ] && { mkdir -p "$D/prev-logs"; mv logs/* "$D/prev-logs/"; }; mkdir -p logs
  export MAX_HEAP_SIZE=${heap}M MAX_DIRECT_MEMORY_SIZE=${direct}M; unset HEAP_NEWSIZE || true
  [ "$NMT" != off ] && export JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=$NMT"
  UNIT="oom-r1v-$(date +%s%N)"
  if [ "$budget" = none ]; then
    systemd-run --user --scope --unit="$UNIT" -- bin/cassandra -f > "$D/stdout.txt" 2>&1 &
  else
    systemd-run --user --scope -p MemoryMax="${budget}M" -p MemorySwapMax=0 --unit="$UNIT" -- bin/cassandra -f > "$D/stdout.txt" 2>&1 &
  fi
  local SP=$!
  ready() { daemon_up || { kill -0 $SP 2>/dev/null || fail "node died at startup"; return 1; }; grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; }
  wait_for "CQL up" 300 ready; unset MAX_HEAP_SIZE MAX_DIRECT_MEMORY_SIZE JVM_EXTRA_OPTS
  PID=$(pgrep -f '^(/usr/bin/)?java .*org[.]apache[.]cassandra[.]service[.]CassandraDaemon' | head -1)
  ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"
  check "-Xmx${heap}M" grep -qx -- "-Xmx${heap}M" "$D/jvm-args.txt"; check "direct ${direct}M" grep -qx -- "-XX:MaxDirectMemorySize=${direct}M" "$D/jvm-args.txt"
  sleep 3; grep -E 'threshold is enabled at|Global buffer pool limit' "$SYSLOG" | grep -v 'Node configuration' | head -4 > "$D/startup-lines.txt" || true
  grep -oE "(memtable_offheap_space|memtable_heap_space|file_cache_size|file_cache_enabled|memtable_cleanup_threshold|memtable_flush_writers|networking_cache_size|memtable_allocation_type)=[^;,]*" "$SYSLOG" | sort -u > "$D/resolved-config.txt" || true
  # expected resolved values (G1: Runtime.maxMemory() = -Xmx)
  local eM=$((heap/4)) eF=$(( heap/4 < 512 ? heap/4 : 512 ))
  [ "$M" != def ] && eM=$M; [ "$F" != def ] && [ "$F" != off ] && eF=$F
  note "expected resolved: memtable_offheap_space=${eM}MiB memtable_heap_space=$((heap/4))MiB file_cache_size=${eF}MiB networking=$(( heap/16 < 128 ? heap/16 : 128 ))MiB"
  grep -q "off-heap threshold is enabled at ${eM}MiB" "$D/startup-lines.txt" || note "WARN: off-heap threshold line does not show ${eM}MiB"
  note "node pid $PID unit $UNIT budget ${budget}MiB heap ${heap}M direct ${direct}M; startup: $(tr '\n' '|' < "$D/startup-lines.txt")"; sleep 5; }
stop_node() { cd "$C"; bin/nodetool stopdaemon >/dev/null 2>&1 || true; for _ in $(seq 60); do daemon_up || break; sleep 1; done
  daemon_up && kill -9 "$PID" 2>/dev/null || true; [ -n "$UNIT" ] && systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; UNIT=""; }
stress() { "$C/tools/bin/cassandra-stress" "$@"; }
nmt() { local tag=$1; [ "$NMT" = off ] && return 0; jcmd "$PID" VM.native_memory summary scale=MB > "$D/nmt-$tag.txt" 2>&1 || true
  note "nmt $tag: $(grep -E '^Total:|^-  *(Java Heap|Class|Thread|Code|GC|Internal|Other|Native Memory Tracking|Symbol|Arena Chunk) ' "$D/nmt-$tag.txt" | sed -E 's/\(reserved=[0-9]+MB, //; s/^- +//; s/ +/ /g' | tr '\n' '|')"; }
start_poller() { [ "$POLL_MS" = 0 ] && { log "poller off"; return 0; }; java -cp "$R/tools" PoolPoller "$PID" "$(cgdir)" "$POLL_MS" "$D/pools.csv" > "$D/poller.err" 2>&1 & POLLER_PID=$!; log "poller pid $POLLER_PID every ${POLL_MS} ms"; }
nmt_loop() { local i=0; while daemon_up; do i=$((i+1)); { echo "epoch_ms $(date +%s%3N) $(grep RssAnon /proc/$PID/status 2>/dev/null)"; jcmd "$PID" VM.native_memory summary scale=MB; } > "$D/nmt-burst-$(printf %03d $i).txt" 2>&1 || true; sleep 5; done; }
monitor() { local p=$1 max=$2 pre=$3 i=0
  while kill -0 "$p" 2>/dev/null && [ $i -lt "$max" ]; do sleep 5; i=$((i+1)); daemon_up || { note "$pre$i: node GONE"; return 1; }; sample "$pre$i"; done; return 0; }
cmd_arm() { local name=$1 budget=$2 heap=$3 M=$4 F=$5 WL=$6
  local direct=${DIRECT:-$(( ${budget/none/16384} / 4 ))}
  D=$L/$name; start_log "$@"; configure_yaml "$M" "$F"; start_node "$budget" "$heap" "$direct" "$M" "$F"
  sample idle; nmt idle; sleep 30; sample idle-nopoll; start_poller; sleep 30; sample idle-poll; local alive=1
  if [[ ",$WL," == *,smoke,* ]]; then note "smoke: startup and idle only, no workload"; fi
  if [[ ",$WL," == *,preload,* ]]; then
    log "+ preload read dataset dataks ($N_DATA partitions)"
    stress write n=$N_DATA no-warmup -col 'size=FIXED(1024)' -schema 'keyspace=dataks' -rate threads=32 > "$D/stress-preload.txt" 2>&1 &
    monitor $! 600 p || alive=0; wait $! 2>/dev/null || true
    if [ $alive = 1 ]; then (cd "$C"; bin/nodetool flush dataks; bin/nodetool disableautocompaction dataks) || true; sample after-preload; stats after-preload; nmt after-preload; fi
  fi
  if [ $alive = 1 ] && [[ ",$WL," == *,cachefill,* ]]; then
    log "+ read pass over dataks to fill the chunk cache ($N_FILL partitions)"
    stress read n=$N_FILL no-warmup -col 'size=FIXED(1024)' -schema 'keyspace=dataks' -pop "seq=1..$N_DATA" -rate threads=64 > "$D/stress-cachefill.txt" 2>&1 &
    monitor $! 600 c || alive=0; wait $! 2>/dev/null || true
    [ $alive = 1 ] && { sample after-cachefill; stats after-cachefill; nmt after-cachefill; }
  fi
  if [ $alive = 1 ] && [[ ",$WL," == *,memburst,* ]]; then
    log "+ write burst into memks ($N_BURST partitions, cap ${BURST_SECS}s)"
    [ "$NMT" != off ] && { nmt_loop & NMTLOOP_PID=$!; }; note "burst start $(date '+%F %T')"
    timeout --signal=INT "$BURST_SECS" "$C/tools/bin/cassandra-stress" write n=$N_BURST no-warmup -col 'size=FIXED(1024)' -schema 'keyspace=memks' -errors retries=50 -rate threads=64 > "$D/stress-memburst.txt" 2>&1 &
    local BP=$!; monitor $BP 120 m || alive=0; wait $BP 2>/dev/null || true; note "burst end $(date '+%F %T')"
    [ -n "$NMTLOOP_PID" ] && { kill "$NMTLOOP_PID" 2>/dev/null || true; wait "$NMTLOOP_PID" 2>/dev/null || true; NMTLOOP_PID=""; }
    [ $alive = 1 ] && { sample after-burst; stats after-burst; for h in 1 2 3 4 5 6; do sleep 5; daemon_up || { alive=0; note "hold$h: node GONE"; break; }; sample hold$h; done; }
  fi
  [ $alive = 1 ] && daemon_up && { sample final; stats final; nmt final; }
  grep -E "Enqueuing flush of (memks|dataks)" "$SYSLOG" > "$D/memtable-flush-lines.txt" 2>/dev/null || true
  grep -E "buffer pool|BufferPool|chunk-cache" "$SYSLOG" | head -20 > "$D/bufferpool-lines.txt" 2>/dev/null || true
  grep -c '^ERROR' "$SYSLOG" > "$D/error-count.txt" 2>/dev/null || echo 0 > "$D/error-count.txt"
  grep -E '^ERROR' "$SYSLOG" | head -20 > "$D/error-lines.txt" || true
  grep -hE 'java.lang.OutOfMemoryError: ' "$D/stdout.txt" "$SYSLOG" 2>/dev/null | head -5 > "$D/oom-jvm.txt" || true
  sudo -n dmesg -T 2>/dev/null | grep -E "Killed process|invoked oom-killer|oom_memcg=.*$UNIT" > "$D/dmesg-all-kills.txt" || true
  grep -F "$UNIT" "$D/dmesg-all-kills.txt" > "$D/dmesg-this-arm.txt" || true
  note "ERROR lines: $(cat "$D/error-count.txt"); JVM OOM lines: $(wc -l < "$D/oom-jvm.txt"); dmesg kills for this scope: $(wc -l < "$D/dmesg-this-arm.txt")"
  if daemon_up; then note "node alive at end"; stop_node; else note "node GONE at end"; [ -n "$UNIT" ] && systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; UNIT=""; fi
  [ -n "$POLLER_PID" ] && { kill "$POLLER_PID" 2>/dev/null || true; wait "$POLLER_PID" 2>/dev/null || true; POLLER_PID=""; }
  log "ARM $name DONE"; }
case "${1:-}" in arm) shift; cmd_arm "$@" ;; *) echo "usage: $0 arm <name> <L_MiB|none> <H_MiB> <M|def> <F|def|off> <workloads>"; exit 2 ;; esac
