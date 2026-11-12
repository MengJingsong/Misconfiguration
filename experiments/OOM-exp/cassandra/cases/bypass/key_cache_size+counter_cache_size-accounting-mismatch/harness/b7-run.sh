#!/usr/bin/env bash
# B7 (OOM-exp, Cassandra 5.0.9, 2026-11-11): key / counter cache accounting mismatch.
# One arm = one clean start of a single node, one cache filled alone through CQL, readings, stop.
#
# Usage:
#   b7-run.sh arm <name> <build: orig|patched> <heap: 512M|2048M|auto> <cache: counter|key> <keyBytes> <fill>
#        fill = target weight as a fraction of the cache capacity C (e.g. 1.5 = overfill to the cap, 0.45 = half fill)
#   b7-run.sh mixed <name> <heap>     defaults, concurrent write + counter_write + read (OOM-contribution test)
#
# Data, logs and dumps: /mydata/b7/{run-<build>,logs/<name>,dumps}. The yaml is the shipped one (no edits): every
# cache and memtable setting is at its default, resolved at the heap used. MAX_HEAP_SIZE is set for 512M/2048M
# and left unset for 'auto' (cassandra-env.sh resolves it from RAM).
set -Eeuo pipefail

B=/mydata/b7
L=$B/logs
DUMPS=$B/dumps
H=$B/harness
LIBCP="$B/run-orig/lib/*"
D=""; S=""; PID=""; C=""; SYSLOG=""

log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
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
  [ "$rc" -ne 0 ] && log "EXIT rc=$rc: stopping clients and node"
  pkill -f '[C]acheFill' 2>/dev/null || true
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) >/dev/null 2>&1 || true
    for _ in $(seq 60); do daemon_up || break; sleep 1; done; fi
  if daemon_up; then log "WARNING: a CassandraDaemon is still running, kill -9"; kill -9 $(pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon') 2>/dev/null || true; fi
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

start_log() { mkdir -p "$L" "$DUMPS"; if [ -e "$D" ] && [ -n "$(ls -A "$D" 2>/dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  log "script: $0 $*"; log "host: $(hostname)"; }

nt() { (cd "$C" && bin/nodetool "$@"); }
cache_lines() { nt info 2>/dev/null | grep -E '^(Key|Counter) Cache' || true; }

start_node() {
  local heap=$1
  cd "$C"
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports 7000/7199/9042 free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042)\b"'
  rm -rf "$C"/data "$C/cassandra.pid"
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then rm -rf logs/*; fi
  mkdir -p logs
  check "yaml is the shipped one" cmp -s conf/cassandra.yaml "$B/cassandra.yaml.shipped"
  cp conf/cassandra.yaml "$D/cassandra.yaml"
  unset HEAP_NEWSIZE MAX_HEAP_SIZE || true
  if [ "$heap" != auto ]; then export MAX_HEAP_SIZE=$heap; fi
  log "+ MAX_HEAP_SIZE=${MAX_HEAP_SIZE:-<unset>} bin/cassandra -p cassandra.pid"
  bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1
  node_ready() { [ -s cassandra.pid ] || return 1
    kill -0 "$(cat cassandra.pid)" 2>/dev/null || fail "node died during startup (see $D/stdout.txt)"
    grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; }
  wait_for "node listening for CQL clients" 300 node_ready
  unset MAX_HEAP_SIZE || true
  PID=$(cat cassandra.pid); note "node pid $PID build $C"
  ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"
  note "jvm: $(grep -E '^-Xm[sx]|^-XX:MaxDirectMemorySize' "$D/jvm-args.txt" | tr '\n' ' ')"
  grep -E 'Initializing (key|counter) cache|Global memtable (on|off)-heap threshold' "$SYSLOG" > "$D/startup-lines.txt" || true
  note "startup: $(tr '\n' '|' < "$D/startup-lines.txt")"
}

stop_node() {
  cd "$C"
  nt drain >/dev/null 2>&1 || true
  nt stopdaemon >/dev/null 2>&1 || true
  for _ in $(seq 60); do daemon_up || break; sleep 1; done
  if daemon_up; then kill -9 "$PID" 2>/dev/null || true; sleep 1; fi
  check "no CassandraDaemon left" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  mkdir -p "$D/node-logs"; cp "$C"/logs/system.log* "$C"/logs/gc.log* "$D/node-logs/" 2>/dev/null || true
}

schema() {
  cd "$C"
  bin/cqlsh -e "CREATE KEYSPACE b7 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
                CREATE TABLE b7.ctr (k blob PRIMARY KEY, c counter);
                CREATE TABLE b7.kv (k blob PRIMARY KEY, v int);" > "$D/schema.txt" 2>&1
  bin/cqlsh -e "DESCRIBE TABLE b7.kv; DESCRIBE TABLE b7.ctr;" >> "$D/schema.txt" 2>&1 || true
}

fill() { # mode table keyBytes first count conc tag
  runto "$D/client-$7.txt" java -Xmx1g -cp "$LIBCP:$H" CacheFill "$1" "$2" "$3" "$4" "$5" "$6"
  note "client $7: $(grep -E '^DONE|^last error' "$D/client-$7.txt" | tr '\n' ' ')"
}

# capacity (bytes), weight (bytes) and entries of one cache, from JMX metrics via nodetool sjk
cache_metric() { # scope name
  nt sjk mx -mg -b "org.apache.cassandra.metrics:type=Cache,scope=$1,name=$2" -f Value 2>/dev/null | tail -1 | tr -d '[:space:]'; }
kreading() { # tag
  local sc=$SCOPE
  local cap w e; cap=$(cache_metric "$sc" Capacity); w=$(cache_metric "$sc" Size); e=$(cache_metric "$sc" Entries)
  note "K[$1] $sc capacity=$cap size=$w entries=$e | $(cache_lines | tr '\n' '|')"
  echo "$cap $w $e"
}

hist() { # tag (forces a full GC)
  runto "$D/class-histo-$1.txt" jcmd "$PID" GC.class_histogram
  runto "$D/heap-$1.txt" jcmd "$PID" GC.heap_info
  note "heap $1: $(grep -E 'garbage-first heap' "$D/heap-$1.txt" | tr -s ' ')"
  note "histo $1 (cache classes): $(grep -E ' (com.github.benmanes.caffeine.cache.PSMW|java.util.concurrent.ConcurrentHashMap\$(Node|TreeNode)|org.apache.cassandra.cache.(CounterCacheKey|KeyCacheKey)|org.apache.cassandra.db.ClockAndCount|org.apache.cassandra.io.sstable.format.big.RowIndexEntry|\[J|\[B)$' "$D/class-histo-$1.txt" | awk '{printf "%s %s %s; ", $4, $2, $3}')"
}

cmd_arm() {
  local name=$1 build=$2 heap=$3 cache=$4 kb=$5 fillf=$6
  D=$L/$name; start_log "$@"
  C=$B/run-$build; SYSLOG=$C/logs/system.log
  note "arm $name: build=$build heap=$heap cache=$cache keyBytes=$kb fill=$fillf"
  start_node "$heap"
  schema
  if [ "$cache" = counter ]; then SCOPE=CounterCache; else SCOPE=KeyCache; fi
  local cap; cap=$(cache_metric $SCOPE Capacity); note "C ($SCOPE capacity) = $cap bytes"
  runto "$D/gc-run-base.txt" jcmd "$PID" GC.run; hist base

  local conc=256 n w0 e0 wpe nfill nins
  if [ "$cache" = counter ]; then
    # calibration: 20,000 entries -> weight per entry
    fill counter ctr "$kb" 0 20000 "$conc" calib
    read -r _ w0 e0 < <(kreading calib | tail -1)
    wpe=$(( w0 / e0 )); nfill=$(python3 -c "import math; print(int(math.ceil($fillf*$cap/$wpe)))")
    note "weight/entry (calibration) = $wpe B; fill to $nfill entries (target weight ${fillf} x C)"
    fill counter ctr "$kb" 20000 $((nfill - 20000)) "$conc" fill
  else
    # insert enough keys for the fill and the churn phase: weight/entry lower bound = keyBytes + 48
    nins=$(python3 -c "import math; print(int(math.ceil(max($fillf,0.5)*1.6*$cap/($kb+48))))")
    fill insert kv "$kb" 0 "$nins" "$conc" insert
    runto "$D/flush.txt" bash -c "cd $C && bin/nodetool flush b7 kv && bin/nodetool compact b7 kv && bin/nodetool tablestats b7.kv | grep -E 'SSTable count|Number of partitions'"
    note "sstables after compact: $(grep -E 'SSTable count' "$D/flush.txt" | tr -s ' ')"
    nt invalidatekeycache
    fill read kv "$kb" 0 20000 "$conc" calib
    read -r _ w0 e0 < <(kreading calib | tail -1)
    wpe=$(( w0 / e0 )); nfill=$(python3 -c "import math; print(min($nins, int(math.ceil($fillf*$cap/$wpe))))")
    note "weight/entry (calibration) = $wpe B; read $nfill keys (target weight ${fillf} x C; $nins inserted)"
    fill read kv "$kb" 20000 $((nfill - 20000)) "$conc" fill
  fi
  sleep 10
  kreading fill >/dev/null
  nt flush >/dev/null 2>&1 || true
  hist fill
  runto "$D/heap-dump.txt" jcmd "$PID" GC.heap_dump "$DUMPS/$name.hprof"
  note "dump: $(ls -l "$DUMPS/$name.hprof" | awk '{print $5}') bytes"
  kreading after-dump >/dev/null
  # sustained: idle window, then churn with new keys (full-fill arms only)
  sleep 60
  kreading idle >/dev/null; hist idle
  if python3 -c "import sys; sys.exit(0 if $fillf >= 1 else 1)"; then
    local nch=$(( nfill / 2 ))
    if [ "$cache" = counter ]; then fill counter ctr "$kb" "$nfill" "$nch" "$conc" churn
    else nch=$(( nins - nfill < nch ? nins - nfill : nch )); fill read kv "$kb" "$nfill" "$nch" "$conc" churn; fi
    sleep 5; kreading churn >/dev/null; hist churn
  fi
  if [ "$cache" = counter ]; then nt invalidatecountercache; else nt invalidatekeycache; fi
  sleep 2; kreading invalidated >/dev/null; hist invalidated
  stop_node
  note "arm $name done"
}

cmd_mixed() {
  local name=$1 heap=$2
  D=$L/$name; start_log "$@"
  C=$B/run-orig; SYSLOG=$C/logs/system.log
  note "mixed arm $name: defaults, heap=$heap, concurrent write + counter_write + read"
  start_node "$heap"
  local ST="$C/tools/bin/cassandra-stress"
  runto "$D/stress-preload.txt" "$ST" write n=500000 -col size='FIXED(1024)' -rate threads=128 -log interval=10
  nt flush >/dev/null
  hist preload
  ( "$ST" write n=3000000 -col size='FIXED(1024)' -rate threads=256 -log interval=10 > "$D/stress-write.txt" 2>&1 ) &
  ( "$ST" counter_write n=2000000 -rate threads=64 -log interval=10 > "$D/stress-counter.txt" 2>&1 ) &
  ( "$ST" read n=4000000 -col size='FIXED(1024)' -pop seq=1..500000 -rate threads=192 -log interval=10 > "$D/stress-read.txt" 2>&1 ) &
  # fix 2026-11-12 (mixed512-r1 lost its samples): wait until the three stress JVMs exist before testing the loop
  # condition; bound every jcmd/nodetool call; cap the window at 30 min wall time.
  local i=0 t0; t0=$(date +%s)
  wait_for "3 stress clients running" 120 bash -c '[ "$(pgrep -fc "[o]rg.apache.cassandra.stress.Stress")" -ge 3 ]'
  while pgrep -f '[o]rg.apache.cassandra.stress.Stress' >/dev/null && [ $(( $(date +%s) - t0 )) -lt 1800 ]; do
    if ! kill -0 "$PID" 2>/dev/null; then note "node died at sample $i"; break; fi
    ( timeout 20 jcmd "$PID" GC.heap_info 2>/dev/null | grep -E 'garbage-first heap' | sed "s/^/[$(date +%T)] /" >> "$D/heap-samples.txt" ) || true
    if [ $((i % 6)) -eq 0 ]; then ( timeout 30 bash -c "cd $C && bin/nodetool info" 2>/dev/null | grep -E '^(Key|Counter) Cache' | sed "s/^/[$(date +%T)] /" >> "$D/cache-samples.txt" ) || true; fi
    sleep 5; i=$((i+1))
  done
  note "window ended after $(( $(date +%s) - t0 )) s; clients still running: $(pgrep -fc '[o]rg.apache.cassandra.stress.Stress' || true)"
  # fix 2026-11-12: a bare 'wait' also waits for the 'exec > >(tee ...)' process substitution and never returns;
  # wait for the stress JVMs by name instead.
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  for _ in $(seq 60); do pgrep -f '[o]rg.apache.cassandra.stress.Stress' >/dev/null || break; sleep 1; done
  pkill -9 -f '[o]rg.apache.cassandra.stress.Stress' 2>/dev/null || true
  note "samples $i; node alive: $(kill -0 "$PID" 2>/dev/null && echo yes || echo no)"
  if kill -0 "$PID" 2>/dev/null; then cache_lines > "$D/cache-final.txt"; hist final; fi
  note "OOM lines: $(grep -c -i 'OutOfMemory' "$C/logs/system.log" 2>/dev/null || echo 0); errors: $(grep -c '^ERROR' "$C/logs/system.log" || echo 0)"
  dmesg -T 2>/dev/null | grep -i -E 'killed process|oom' | tail -5 > "$D/dmesg-oom.txt" || true
  for f in write counter read; do note "stress $f: $(grep -E '^(Op rate|Total errors|Total operation time)' "$D/stress-$f.txt" | tr -s ' ' | tr '\n' '|')"; done
  if ls "$C"/*.hprof >/dev/null 2>&1; then mv "$C"/*.hprof "$DUMPS/$name.hprof"; note "OOM dump kept: $DUMPS/$name.hprof"; fi
  if kill -0 "$PID" 2>/dev/null; then stop_node; else mkdir -p "$D/node-logs"; cp "$C"/logs/system.log* "$C"/logs/gc.log* "$D/node-logs/" 2>/dev/null || true; fi
  note "arm $name done"
}

case "${1:-}" in
  arm)   shift; cmd_arm "$@" ;;
  mixed) shift; cmd_mixed "$@" ;;
  *) echo "usage: $0 arm <name> <orig|patched> <512M|2048M|auto> <counter|key> <keyBytes> <fill> | mixed <name> <heap>"; exit 2 ;;
esac
