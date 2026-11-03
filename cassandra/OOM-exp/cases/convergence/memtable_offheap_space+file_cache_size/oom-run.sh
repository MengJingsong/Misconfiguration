#!/usr/bin/env bash
# OOM-exp convergence run 7: memtable_offheap_space + file_cache_size (chunk cache on).
# Budget: cgroup v2 memory.max on the whole JVM (systemd-run --user --scope), as in runs 4-6.
# Both pools are native/direct memory read as RssAnon:
#   memtable_offheap_space: memtable_allocation_type=offheap_objects -> NativeAllocator ->
#     MemoryUtil.allocate (malloc); memtable_cleanup_threshold=0.99 so writers park at the limit.
#   file_cache_size: file_cache_enabled=true -> ChunkCache (Caffeine, maximumWeight = size - reserved)
#     over BufferPools.forChunkCache() (direct macro chunks, threshold = file_cache_size).
# Usage: oom-run.sh baseline <budget>
#        oom-run.sh arm <name> <budget> <M_MiB> <F_MiB> <workloads: preload,cachefill,memburst>
set -Eeuo pipefail
C=$HOME/cassandra-run1; L=$HOME/oom-offheap-run7/logs; SYSLOG=$C/logs/system.log
XMX=${XMX:-768M}; HEAPMEM=${HEAPMEM:-200}
N_DATA=${N_DATA:-800000}      # read dataset partitions (5 x 1 KiB cols ~ 5 KiB each)
N_BURST=${N_BURST:-2000000}   # memtable write-burst partitions
BURST_SECS=${BURST_SECS:-240} # cap on the write burst
D=""; S=""; PID=""; UNIT=""
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
wait_for() { local d=$1 t=$2 i=0; shift 2; until "$@"; do sleep 1; i=$((i+1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s: $d"; done; log "ok: $d (${i}s)"; }
daemon_up() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' >/dev/null; }
cleanup() { local rc=$?; trap - EXIT ERR
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) >/dev/null 2>&1 || true; for _ in $(seq 60); do daemon_up || break; sleep 1; done; fi
  daemon_up && kill -9 $(pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon') 2>/dev/null || true
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
  sed -i -e "s/^# memtable_heap_space: 2048MiB\$/memtable_heap_space: ${HEAPMEM}MiB/" \
         -e "s/^# memtable_offheap_space: 2048MiB\$/memtable_offheap_space: ${M}MiB/" \
         -e "s/^memtable_allocation_type: heap_buffers\$/memtable_allocation_type: offheap_objects/" \
         -e "s/^# memtable_cleanup_threshold: 0.11\$/memtable_cleanup_threshold: 0.99/" \
         -e "s/^# file_cache_enabled: false\$/file_cache_enabled: true/" \
         -e "s/^# file_cache_size: 512MiB\$/file_cache_size: ${F}MiB/" "$Y"
  git -C "$C" diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  for k in "memtable_heap_space: ${HEAPMEM}MiB" "memtable_offheap_space: ${M}MiB" "memtable_allocation_type: offheap_objects" "memtable_cleanup_threshold: 0.99" "file_cache_enabled: true" "file_cache_size: ${F}MiB"; do
    grep -qx "$k" "$Y" || fail "yaml edit missing: $k"; done
  note "yaml: M=${M}MiB F=${F}MiB heap_space=${HEAPMEM}MiB offheap_objects cleanup=0.99 chunk cache on"; }
start_node() { local budget=$1; cd "$C"
  check "no daemon" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042)\b"'
  rm -rf "$C"/data/*; [ -n "$(ls -A logs 2>/dev/null)" ] && { mkdir -p "$D/prev-logs"; mv logs/* "$D/prev-logs/"; }; mkdir -p logs
  export MAX_HEAP_SIZE=$XMX; unset HEAP_NEWSIZE || true
  UNIT="oom-run7-$(date +%s%N)"
  systemd-run --user --scope -p MemoryMax="${budget}M" -p MemorySwapMax=0 --unit="$UNIT" -- bin/cassandra -f > "$D/stdout.txt" 2>&1 &
  local SP=$!
  ready() { daemon_up || { kill -0 $SP 2>/dev/null || fail "node died at startup"; return 1; }; grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; }
  wait_for "CQL up" 300 ready; unset MAX_HEAP_SIZE
  PID=$(pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' | head -1)
  ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"; check "-Xmx$XMX" grep -qx -- "-Xmx$XMX" "$D/jvm-args.txt"
  grep -E 'off-heap threshold|ChunkCache|chunk cache|Global memtable' "$SYSLOG" | head -5 > "$D/startup-lines.txt" || true
  note "node pid $PID unit $UNIT budget ${budget}MiB; startup: $(tr '\n' '|' < "$D/startup-lines.txt")"; sleep 5; }
stop_node() { cd "$C"; bin/nodetool stopdaemon >/dev/null 2>&1 || true; for _ in $(seq 60); do daemon_up || break; sleep 1; done
  daemon_up && kill -9 "$PID" 2>/dev/null || true; [ -n "$UNIT" ] && systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; UNIT=""; }
stress() { "$C/tools/bin/cassandra-stress" "$@"; }
monitor() { # sample every 5 s while pid $1 runs (max $2 samples); prefix $3
  local p=$1 max=$2 pre=$3 i=0
  while kill -0 "$p" 2>/dev/null && [ $i -lt "$max" ]; do sleep 5; i=$((i+1)); daemon_up || { note "$pre$i: node GONE"; return 1; }; sample "$pre$i"; done; return 0; }
cmd_arm() { local name=$1 budget=$2 M=$3 F=$4 WL=$5
  D=$L/$name; start_log "$@"; configure_yaml "$M" "$F"; start_node "$budget"; sample idle; local alive=1
  if [[ ",$WL," == *,preload,* ]]; then
    log "+ preload read dataset dataks ($N_DATA partitions)"
    stress write n=$N_DATA no-warmup -col 'size=FIXED(1024)' -schema 'keyspace=dataks' -rate threads=32 > "$D/stress-preload.txt" 2>&1 &
    monitor $! 400 p || alive=0; wait $! 2>/dev/null || true
    if [ $alive = 1 ]; then (cd "$C"; bin/nodetool flush dataks; bin/nodetool disableautocompaction dataks) || true; sample after-preload; stats after-preload; fi
  fi
  if [ $alive = 1 ] && [[ ",$WL," == *,cachefill,* ]]; then
    log "+ read pass over dataks to fill the chunk cache"
    stress read n=$N_DATA no-warmup -col 'size=FIXED(1024)' -schema 'keyspace=dataks' -pop "seq=1..$N_DATA" -rate threads=64 > "$D/stress-cachefill.txt" 2>&1 &
    monitor $! 400 c || alive=0; wait $! 2>/dev/null || true
    [ $alive = 1 ] && { sample after-cachefill; stats after-cachefill; }
  fi
  if [ $alive = 1 ] && [[ ",$WL," == *,memburst,* ]]; then
    log "+ write burst into memks ($N_BURST partitions, cap ${BURST_SECS}s)"
    timeout --signal=INT "$BURST_SECS" "$C/tools/bin/cassandra-stress" write n=$N_BURST no-warmup -col 'size=FIXED(1024)' -schema 'keyspace=memks' -errors retries=50 -rate threads=64 > "$D/stress-memburst.txt" 2>&1 &
    monitor $! 120 m || alive=0; wait $! 2>/dev/null || true
    [ $alive = 1 ] && { sample after-burst; stats after-burst; for h in 1 2 3 4 5 6; do sleep 5; daemon_up || { alive=0; note "hold$h: node GONE"; break; }; sample hold$h; done; }
  fi
  [ $alive = 1 ] && daemon_up && { sample final; stats final; }
  grep -c '^ERROR' "$SYSLOG" > "$D/error-count.txt" 2>/dev/null || echo 0 > "$D/error-count.txt"
  grep -E '^ERROR' "$SYSLOG" | head -20 > "$D/error-lines.txt" || true
  grep -hE 'java.lang.OutOfMemoryError: ' "$D/stdout.txt" "$SYSLOG" 2>/dev/null | head -5 > "$D/oom-jvm.txt" || true
  sudo -n dmesg -T 2>/dev/null | grep -E "Killed process|invoked oom-killer|oom_memcg=.*$UNIT" > "$D/dmesg-all-kills.txt" || true
  grep -F "$UNIT" "$D/dmesg-all-kills.txt" > "$D/dmesg-this-arm.txt" || true
  note "ERROR lines: $(cat "$D/error-count.txt"); JVM OOM lines: $(wc -l < "$D/oom-jvm.txt"); dmesg kills for this scope: $(wc -l < "$D/dmesg-this-arm.txt")"
  if daemon_up; then note "node alive at end"; stop_node; else note "node GONE at end"; [ -n "$UNIT" ] && systemctl --user stop "$UNIT" >/dev/null 2>&1 || true; UNIT=""; fi
  log "ARM $name DONE"; }
case "${1:-}" in arm) shift; cmd_arm "$@" ;; *) echo "usage: $0 arm <name> <budget> <M> <F> <workloads>"; exit 2 ;; esac
