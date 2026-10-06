#!/usr/bin/env bash
# Stage 4, run 1, cluster tier — memtable_heap_space-tryAllocate-limit, case §9e.
#
#   cluster-run.sh instrument              §9e "before the cluster tier", step 1
#   cluster-run.sh value <label> <prev>    one capacity value, end to end
#       label: 128 | 256 | 512 | default | cleanup256 (control: 256 MiB, default threshold, no C)
#       prev : label of the run before, or "pre-cluster"; its logs/ is moved to <prev dir>/logs
#   cluster-run.sh rest                    256, 512, default, cleanup256, in that order
#   cluster-run.sh heap                    real-heap pass: all five values, A and B only (no C), folders <value>-heap
#
# Logs every command with its output to ~/stage4-logs/cluster/<value>/session.log; the
# readings go to <value>/summary.txt. Exits non-zero at the first failed check (exit 3: writers
# never waited in B, the §9c branch). On any non-zero exit it stops stress and the node.
set -Eeuo pipefail

H=/proj/misconfiguration-PG0/git-repos/misconfiguration/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/memtable_heap_space-tryAllocate-limit
C=$HOME/cassandra-run1
L=$HOME/stage4-logs/cluster
RULE=$H/escape-hatch.btm
BM=$C/build/lib/jars
BEAN='org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation'
ROWS=${ROWS:-2000000}; COLSIZE=${COLSIZE:-1024}; THREADS=${THREADS:-256}   # §9c values; overridable for its step-ups
SYSLOG=$C/logs/system.log
STRESS_PID=""; D=""; S=""

log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
run()  { log "+ $*"; "$@"; local rc=$?; log "  rc=$rc"; return $rc; }
runto(){ local f=$1; shift; log "+ $* > $f"; local rc=0; "$@" > "$f" 2>&1 || rc=$?
  log "  rc=$rc ($(wc -l < "$f") lines in $f)"; [ "$(wc -l < "$f")" -le 40 ] && sed 's/^/    | /' "$f" >&2; return $rc; }
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
  daemon_up && log "WARNING: a CassandraDaemon is still running"
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

start_log() { mkdir -p "$L"; if [ -e "$D" ] && [ -n "$(ls -A "$D" 2>/dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  log "script: $0 $*"; log "host: $(hostname)"; }

# ---------------------------------------------------------------- instrument check
instrument() {
  D=$L/instrument-check.d; start_log
  local T=$L/instrument-check.txt; rm -f "$T"
  cd "$C"
  if cmp -s "$H/HeapPoolTest.java" test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java; then log "HeapPoolTest in clone = harness copy"
  else run cp "$H/HeapPoolTest.java" test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java; fi
  runto "$D/ant.txt" ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest \
    "-Dtest.jvm.args=-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:$RULE -Dstage4.byteman.out=$T" || { tail -30 "$D/ant.txt"; fail "ant testsome failed"; }
  grep -E 'Tests run:|BUILD' "$D/ant.txt" | tee "$D/ant-summary.txt"
  check "HeapPoolTest: 2 tests, no failures" grep -q 'Tests run: 2, Failures: 0, Errors: 0' "$D/ant.txt"
  check "trace file exists" test -s "$T"
  log "trace: $(cat "$T")"
  check "trace has exactly one line" test "$(wc -l < "$T")" -eq 1
  check "trace line is forced=1 limit=100" grep -q -E '^forced=1 limit=100 ' "$T"
  log "INSTRUMENT CHECK PASSED"
}

# ---------------------------------------------------------------- readings
mx() { local raw; raw=$(cd "$C" && bin/nodetool sjk mx -mg -b "$BEAN" -f "$1" 2>&1) || { log "sjk failed: $raw"; return 1; }
  log "sjk $1 raw: $(echo "$raw" | tr '\n' '|')"; echo "$raw" | awk 'NF{l=$0} END{n=split(l,a,/[ \t:=]+/); print a[n]}'; }
count() { local v; v=$(mx Count); [[ "$v" =~ ^[0-9]+$ ]] || fail "BlockedOnAllocation Count not an integer: '$v' (sjk read-out defect)"; echo "$v"; }
nflush() { grep -c -E 'Enqueuing flush of .*Reason: MEMTABLE_LIMIT' "$SYSLOG" || true; }
ncomplete() { grep -c 'Completed flushing' "$SYSLOG" || true; }
wait_flushes() { local n=$1 t=$2 i=0   # limit-driven flushes seen >= n
  while [ "$(nflush)" -lt "$n" ]; do
    kill -0 "$STRESS_PID" 2>/dev/null || fail "stress exited before limit-driven flush #$n (tail of stress.txt: $(tail -3 "$D/stress.txt" | tr '\n' '|'))"
    sleep 0.5; i=$((i+1)); [ "$i" -ge $((t*2)) ] && fail "timeout ${t}s waiting for limit-driven flush #$n"
  done; log "limit-driven flush #$n seen after ~$((i/2))s"; }
heap_sample() { local tag=$1   # 9d "Real heap": GC.run, then GC.heap_info
  runto "$D/gc-run-$tag.txt" jcmd "$PID" GC.run
  runto "$D/heap-$tag.txt" jcmd "$PID" GC.heap_info
  note "real heap $tag: $(grep -E 'heap +total' "$D/heap-$tag.txt" | sed 's/  */ /g'); last 'Used total' line: $(grep 'Used total' "$SYSLOG" | tail -1 | sed -E 's/.*(Used total: [^,]*),.*/\1/')"; }
percentiles() { local a; for a in Count 50thPercentile 95thPercentile 99thPercentile Max; do note "  BlockedOnAllocation $a = $(mx $a)"; done; }
window() { # from to  -> "N calls, B bytes"
  awk -F'[= ]' -v from="$1" -v to="$2" '$6>=from && $6<to {n++; s+=$2} END {print n+0 " calls, " s+0 " bytes"}' "$TRACE"; }

# ---------------------------------------------------------------- one capacity value
value() {
  local label=$1 prev=${2:-pre-cluster} KNOB="" CLEAN=0.99 RUNC=1 DIR; PID=""
  case $label in
    128|256|512) DIR=${label}MiB; KNOB=$label ;;
    default)     DIR=default ;;
    cleanup256)  DIR=256MiB-cleanup-default; KNOB=256; CLEAN=""; RUNC=0 ;;
    *) echo "unknown label $label" >&2; exit 2 ;;
  esac
  DIR=$DIR${DIRSUFFIX:-}; [ "${STOP_AFTER_B:-0}" = 1 ] && RUNC=0
  D=$L/$DIR; start_log "$@"; cd "$C"
  TRACE=$D/escape-hatch.txt
  note "== $DIR: knob=${KNOB:-unset} cleanup_threshold=${CLEAN:-default} scenario C=$([ $RUNC = 1 ] && echo yes || echo no); stress n=$ROWS size=$COLSIZE threads=$THREADS"

  # --- preflight
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "ports 7000/7199/9042/9091 free" bash -c '! ss -ltn | grep -q -E ":(7000|7199|9042|9091)\b"'
  check "local disk has >= 20 GB free" test "$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)" -ge 20

  # --- config (9b): pristine yaml + only the edits below
  runto conf/cassandra.yaml git show HEAD:conf/cassandra.yaml
  sed -i -e 's/^memtable_allocation_type: heap_buffers$/memtable_allocation_type: unslabbed_heap_buffers/' conf/cassandra.yaml
  [ -n "$KNOB" ]  && sed -i -e "s/^# memtable_heap_space: 2048MiB\$/memtable_heap_space: ${KNOB}MiB/" conf/cassandra.yaml
  [ -n "$CLEAN" ] && sed -i -e "s/^# memtable_cleanup_threshold: 0.11\$/memtable_cleanup_threshold: $CLEAN/" conf/cassandra.yaml
  local want got
  want=$( { [ -n "$KNOB" ] && echo "memtable_heap_space: ${KNOB}MiB"; [ -n "$CLEAN" ] && echo "memtable_cleanup_threshold: $CLEAN"; echo "memtable_allocation_type: unslabbed_heap_buffers"; } )
  got=$(grep -E '^(memtable_heap_space|memtable_cleanup_threshold|memtable_allocation_type):' conf/cassandra.yaml)
  log "yaml memtable lines: $(echo "$got" | tr '\n' '|')"
  check "yaml has exactly the expected memtable lines" test "$got" = "$want"
  git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  check "yaml diff has $(echo "$want" | wc -l) added lines" test "$(grep -c '^+[^+]' "$D/cassandra.yaml.diff")" -eq "$(echo "$want" | wc -l)"
  note "yaml diff: $(grep '^[+-][^+-]' "$D/cassandra.yaml.diff" | tr '\n' '|')"

  # --- reset (9b) + move logs/ (9e, amended)
  [ "$C" = "$HOME/cassandra-run1" ] || fail "unexpected clone path $C"
  rm -rf "$C"/data/* "$C/cassandra.pid"
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then
    mkdir -p "$L/$prev"; local dest=$L/$prev/logs; [ -e "$dest" ] && dest=$dest.$(date +%s)
    run mv logs "$dest"
  fi
  mkdir -p logs

  # --- start the node (9e step 2)
  export MAX_HEAP_SIZE=4G; unset HEAP_NEWSIZE || true
  export JVM_EXTRA_OPTS="-javaagent:$BM/byteman-4.0.20.jar=script:$RULE,listener:true -Dstage4.byteman.out=$TRACE"
  note "MAX_HEAP_SIZE=$MAX_HEAP_SIZE"; note "JVM_EXTRA_OPTS=$JVM_EXTRA_OPTS"
  log "+ bin/cassandra -p cassandra.pid > $D/stdout.txt 2>&1"
  bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1
  node_ready() { [ -s cassandra.pid ] || return 1
    kill -0 "$(cat cassandra.pid)" 2>/dev/null || fail "node process died during startup (see $D/stdout.txt)"
    grep -q 'Starting listening for CQL clients' "$SYSLOG" 2>/dev/null; }
  wait_for "node listening for CQL clients" 300 node_ready
  unset JVM_EXTRA_OPTS MAX_HEAP_SIZE   # node is up; keep the agent (port 9091) out of stress, nodetool and cqlsh JVMs
  PID=$(cat cassandra.pid); note "node pid $PID"
  ps -o args= -p "$PID" | tr ' ' '\n' > "$D/jvm-args.txt"
  check "JVM has -Xms4G and -Xmx4G" bash -c "grep -qx -- '-Xms4G' '$D/jvm-args.txt' && grep -qx -- '-Xmx4G' '$D/jvm-args.txt'"
  check "JVM has the Byteman agent" grep -q 'byteman-4.0.20.jar' "$D/jvm-args.txt"

  # --- instrument in place
  runto "$D/submit-l.txt" java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit -l
  check "Submit -l lists the allocated(long) trigger" grep -q -F 'trigger method: org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator.allocated(long) void' "$D/submit-l.txt"

  # --- confirmation lines (9b)
  local l1 l2 mib
  l1=$(grep -m1 'Global memtable on-heap threshold is enabled at' "$SYSLOG" || true); l2=$(grep -m1 'Memtables allocating with on-heap buffers' "$C/logs/debug.log" || true)
  note "system.log: $l1"; note "debug.log:  $l2"
  [ -n "$l2" ] || fail "debug.log has no 'Memtables allocating with on-heap buffers' (HeapPool not built)"
  mib=$(echo "$l1" | sed -n 's/.*enabled at \([0-9]*\)MiB.*/\1/p'); [ -n "$mib" ] || fail "cannot read the on-heap limit from: '$l1'"
  local LIMIT=$((mib*1048576)); note "resolved on-heap limit: ${mib}MiB = $LIMIT bytes"
  if [ -n "$KNOB" ]; then check "resolved limit = knob ($KNOB MiB)" test "$mib" -eq "$KNOB"
  else check "default limit is about 1024 MiB (1000..1024)" test "$mib" -ge 1000 -a "$mib" -le 1024; fi
  grep -E 'memtable|Memtable' "$SYSLOG" | head -20 > "$D/startup-memtable-lines.txt" || true

  # --- control run: idle heap and idle wait count
  runto "$D/gc-run-idle.txt" jcmd "$PID" GC.run
  runto "$D/heap-idle.txt" jcmd "$PID" GC.heap_info
  note "idle real heap: $(grep -E 'heap +total' "$D/heap-idle.txt" | sed 's/  */ /g')"
  local C_IDLE; C_IDLE=$(count); note "idle BlockedOnAllocation Count = $C_IDLE"

  # --- scenario A
  run bin/cqlsh -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1} AND durable_writes = false;"
  bin/cqlsh -e "DESCRIBE KEYSPACE keyspace1" > "$D/keyspace1.txt" 2>&1
  check "keyspace1 has durable_writes = false" grep -q 'durable_writes = false' "$D/keyspace1.txt"
  local T_A0 T_A1 T_C0 T_STOP
  T_A0=$(now); log "+ tools/bin/cassandra-stress write n=$ROWS no-warmup -col 'size=FIXED($COLSIZE)' -rate threads=$THREADS   (T_A0=$T_A0)"
  tools/bin/cassandra-stress write n="$ROWS" no-warmup -col "size=FIXED($COLSIZE)" -rate threads="$THREADS" > "$D/stress.txt" 2>&1 &
  STRESS_PID=$!
  wait_flushes 1 1200; T_A1=$(now)
  local C_A; C_A=$(count)
  note "A: T_A0=$T_A0 T_A1=$T_A1 (ms), first limit flush after $((T_A1-T_A0)) ms; BlockedOnAllocation Count = $C_A"
  note "A 'Used total' line:   $(grep -m1 'Used total' "$SYSLOG" | cut -c1-300 || true)"
  heap_sample endA
  note "A 'Enqueuing' line:    $(grep -m1 -E 'Enqueuing flush of .*Reason: MEMTABLE_LIMIT' "$SYSLOG" | cut -c1-300 || true)"

  # --- scenario B: three more limit-driven flushes, one thread dump during each
  local k
  for k in 2 3 4; do
    wait_flushes "$k" 900
    log "+ jcmd $PID Thread.print > threaddump-B$((k-1)).txt   (flushes enqueued=$(nflush) completed=$(ncomplete))"
    jcmd "$PID" Thread.print > "$D/threaddump-B$((k-1)).txt" 2>&1
    note "B dump $((k-1)): at limit-flush #$k (all-Completed-flushing lines so far: $(ncomplete)); frames at MemtableAllocator.java:195 = $(grep -c 'MemtableAllocator.java:195' "$D/threaddump-B$((k-1)).txt" || true)"
  done
  local C_B; C_B=$(count); note "B end: $(now) ms; BlockedOnAllocation Count before B (at A) = $C_A, after B = $C_B"; percentiles
  heap_sample endB
  bin/nodetool tablestats > "$D/tablestats-B.txt" 2>&1 || true
  note "B tablestats: memtable cells outside keyspace1: $(awk '/^Keyspace :/{ks=$3} /Table: /{t=$NF} /Memtable cell count:/{if ($NF>0 && ks!="keyspace1") printf "%s.%s=%s ", ks, t, $NF}' "$D/tablestats-B.txt")"
  note "B Enqueuing flush reasons so far: $(grep 'Enqueuing flush' "$SYSLOG" | grep -o 'Reason: [A-Z_]*' | sort | uniq -c | tr '\n' ';')"
  if [ -n "$CLEAN" ] && [ "$C_B" -le "$C_IDLE" ]; then
    note "B: BlockedOnAllocation Count did not rise (idle $C_IDLE, B $C_B): no writer waited. Runbook 9c: stop, reset, repeat with threads=512."
    exit 3
  fi

  # --- scenario C: escape hatch
  if [ "$RUNC" = 1 ]; then
    local c1 c2 i=0
    while :; do c1=$(count); sleep 3; c2=$(count); [ "$c2" -gt "$c1" ] && break
      kill -0 "$STRESS_PID" 2>/dev/null || fail "stress exited before the wait count was rising"
      i=$((i+1)); [ "$i" -ge 60 ] && fail "BlockedOnAllocation Count never rising before C"; done
    note "C: count rising ($c1 -> $c2)"
    local L0; L0=$(wc -l < "$SYSLOG"); T_C0=$(now)
    log "+ bin/nodetool flush keyspace1 standard1   (T_C0=$T_C0)"
    local t0=$SECONDS; run bin/nodetool flush keyspace1 standard1; note "C: nodetool flush returned rc=0 after $((SECONDS-t0)) s (T_C0=$T_C0)"
    tail -n +$((L0+1)) "$SYSLOG" > "$D/system-log-after-C0.txt"
    note "C 'Enqueuing flush' lines since T_C0: $(grep -c 'Enqueuing flush' "$D/system-log-after-C0.txt" || true); reasons: $(grep 'Enqueuing flush' "$D/system-log-after-C0.txt" | grep -o 'Reason: [A-Z_]*' | sort | uniq -c | tr '\n' ';')"
    note "C 'Used total' on-heap ratios since T_C0: $(sed -n 's/.*Used total: \([0-9.]*\)\/.*/\1/p' "$D/system-log-after-C0.txt" | tr '\n' ' ')"
    note "C 'Used total' above 1.00: $(sed -n 's/.*Used total: \([0-9.]*\)\/.*/\1/p' "$D/system-log-after-C0.txt" | awk '$1>1.00' | tr '\n' ' ')(end)"
  else T_C0=$(now); fi
  note "whole run: max 'Used total' on-heap ratio = $(sed -n 's/.*Used total: \([0-9.]*\)\/.*/\1/p' "$SYSLOG" | sort -n | tail -1)"

  # --- stop, then read the trace (9e step 5)
  pkill -f '[o]rg.apache.cassandra.stress.Stress' || true; wait "$STRESS_PID" 2>/dev/null || true; STRESS_PID=""
  note "stress log: $(grep -c -i -E 'exception|timed out|error' "$D/stress.txt" || true) lines mention exception/timeout/error; last line: $(tail -1 "$D/stress.txt" | cut -c1-160)"
  T_STOP=$(now); run bin/nodetool stopdaemon
  wait_for "node process gone" 120 bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "pgrep prints nothing after stopdaemon" bash -c '[ -z "$(pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon")" ]'
  note "windows (ms): T_A0=$T_A0 T_A1=$T_A1 T_C0=$T_C0 T_STOP=$T_STOP"
  if [ -s "$TRACE" ]; then
    note "trace total: $(awk -F'[= ]' '{n++; s+=$2} END {print n+0 " calls, " s+0 " bytes"}' "$TRACE")"
    note "trace A [T_A0,T_A1):  $(window "$T_A0" "$T_A1")"
    note "trace B [T_A1,T_C0):  $(window "$T_A1" "$T_C0")"
    [ "$RUNC" = 1 ] && note "trace C [T_C0,T_STOP): $(window "$T_C0" "$T_STOP")" || note "trace after B [T_C0,T_STOP): $(window "$T_C0" "$T_STOP")"
    note "trace: distinct limit values: $(awk -F'[= ]' '{print $4}' "$TRACE" | sort -u | tr '\n' ' ')(knob in bytes = $LIMIT)"
  else note "trace: no file, so no allocation was forced through (Submit -l showed the rule was loaded)"; fi
  grep -E 'Enqueuing flush|Flushing largest|Completed flushing|Global memtable|ERROR|WARN' "$SYSLOG" > "$D/system-log-key-lines.txt" || true
  note "system.log key lines saved: $(wc -l < "$D/system-log-key-lines.txt") lines"
  if [ -s "$TRACE" ]; then
    check "every trace line's limit equals the knob in bytes ($LIMIT)" bash -c "[ \"\$(awk -F'[= ]' -v L=$LIMIT '\$4!=L{b++} END{print b+0}' '$TRACE')\" -eq 0 ]"
  fi
  note "== $DIR: COMPLETE"
}

# ---------------------------------------------------------------- everything after 128
rest() {
  mkdir -p "$L"; exec > >(tee -a "$L/rest.log") 2>&1
  local pair v p
  for pair in "256 128" "512 256" "default 512" "cleanup256 default"; do
    set -- $pair; v=$1; p=$2
    p=$( case $p in 128|256|512) echo ${p}MiB;; *) echo $p;; esac )
    log "===== value $v (previous: $p)"
    "$0" value "$v" "$p" || { log "value $v FAILED rc=$?"; exit 1; }
  done
  mkdir -p "$L/256MiB-cleanup-default"; [ -e "$L/256MiB-cleanup-default/logs" ] || mv "$C/logs" "$L/256MiB-cleanup-default/logs"
  log "ALL DONE"
}

heap() {
  mkdir -p "$L"; exec > >(tee -a "$L/heap-pass.log") 2>&1
  export DIRSUFFIX=-heap STOP_AFTER_B=1
  local pair v p
  for pair in "128 pre-heap-pass" "256 128MiB-heap" "512 256MiB-heap" "default 512MiB-heap" "cleanup256 default-heap"; do
    set -- $pair; v=$1; p=$2
    log "===== heap pass, value $v (previous: $p)"
    "$0" value "$v" "$p" || { log "value $v FAILED rc=$?"; exit 1; }
  done
  mkdir -p "$L/256MiB-cleanup-default-heap"; [ -e "$L/256MiB-cleanup-default-heap/logs" ] || mv "$C/logs" "$L/256MiB-cleanup-default-heap/logs"
  log "HEAP PASS DONE"
}

case ${1:-} in
  heap) heap ;;
  instrument) instrument ;;
  value) shift; value "$@" ;;
  rest) rest ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
