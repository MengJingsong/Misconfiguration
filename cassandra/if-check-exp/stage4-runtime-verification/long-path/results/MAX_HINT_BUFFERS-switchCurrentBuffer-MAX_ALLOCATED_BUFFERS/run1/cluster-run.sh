#!/usr/bin/env bash
# Stage 4, run 1, cluster tier — MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS, case §9b–§9e.
#
# Runs on node 1 (node0, ~/cassandra-run1). Node 2 (pc80) must already be a ring member and be STOPPED: run
# ring.sh from the workstation once first (it leaves both nodes stopped with the ring's data in place).
#
#   cluster-run.sh smoke            single node, no ring: tests this script's own helpers, then wipes data/ and logs/.
#                                   Refuses to run if data/ exists (it would destroy the ring).
#   cluster-run.sh value <label>    one capacity value, end to end. Labels:
#                                     n2 | n3 | n6        MAX_HINT_BUFFERS = 2, 3 (default), 6; 32 MiB buffers
#                                     n3-buf64MiB         second-knob arm: n = 3, max_mutation_size 32MiB and
#                                                         commitlog_segment_size 64MiB, so 64 MiB buffers
#                                     n3-natural          natural-load control: n = 3, the hold is never loaded
#   cluster-run.sh all              n2, n3, n6, n3-buf64MiB, n3-natural, in that order
#
# Per value (case 9e): preflight, config, reset, start node 1 with hints-pool.btm, Submit -l check, control
# run, scenario A (load the hold, write until created=<n>), scenario B (keep writing ~60 s under the hold,
# sample, dump threads), release the hold, stop, read the traces. Every command is logged with its output to
# ~/stage4-logs/hints/cluster/<label>/session.log; readings go to readings.csv and summary.txt there.
#
# Exit codes: 1 a check failed (an instrument or set-up fault); 2 usage; 3 scenario A never reached
# created=<n> (invalid run, case 9a/9c: fix the workload and repeat); any non-zero exit stops stress and node 1.
# Overridable: THREADS (64), ROWS (200000), HOLD_MS (3000), B_SECONDS (60), A_TIMEOUT (180).
set -Eeuo pipefail

C=$HOME/cassandra-run1
HARNESS=$HOME/stage4-harness-run/hints           # copy of the committed harness, with SHA256SUMS
L=$HOME/stage4-logs/hints/cluster
BM=$C/build/lib/jars
IP1=198.22.255.77                                 # node 1 (this node)
IP2=198.22.255.91                                 # node 2 (pc80), stopped
THREADS=${THREADS:-64}; ROWS=${ROWS:-200000}; HOLD_MS=${HOLD_MS:-3000}
B_SECONDS=${B_SECONDS:-60}; A_TIMEOUT=${A_TIMEOUT:-180}
DIRECT='java.nio:type=BufferPool,name=direct'
D=""; S=""; PID=""; STRESS_PID=""; MODE=""

# ---------------------------------------------------------------- helpers
log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
run()  { log "+ $*"; "$@"; local rc=$?; log "  rc=$rc"; return $rc; }
runto(){ local f=$1; shift; log "+ $* > $f"; local rc=0; "$@" > "$f" 2>&1 || rc=$?
  log "  rc=$rc ($(wc -l < "$f") lines in $f)"; [ "$(wc -l < "$f")" -le 40 ] && sed 's/^/    | /' "$f" >&2; return $rc; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
expect(){ local d=$1; shift; if "$@"; then note "EXPECTED: $d — yes"; else note "EXPECTED: $d — NO (recorded; the AI judges it in the results file)"; fi; }
daemon_up() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' > /dev/null; }
submit() { (cd "$C" && java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit "$@" 2>&1); }

cleanup() {
  local rc=$?; trap - EXIT ERR
  [ "$rc" -ne 0 ] && log "EXIT rc=$rc: stopping stress and node 1"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2> /dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) > /dev/null 2>&1 || true
    for _ in $(seq 60); do daemon_up || break; sleep 1; done; fi
  daemon_up && log "WARNING: a CassandraDaemon is still running"
  [ -d "$C/conf" ] && mk_yaml 0 2> /dev/null || true        # leave the clone with the ring edits only
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

# The yaml is always rebuilt from the tag plus the ring edits, and in the second-knob arm the two lines of case 9b.
mk_yaml() {   # 0 = ring edits only; 1 = second-knob arm
  cd "$C"
  git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
  sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'stage4-hints'/" \
         -e "s/^      - seeds: \"127.0.0.1:7000\"/      - seeds: \"$IP1:7000\"/" \
         -e "s/^listen_address: localhost/listen_address: $IP1/" conf/cassandra.yaml
  [ "$1" = 1 ] && sed -i -e 's/^commitlog_segment_size: 32MiB$/commitlog_segment_size: 64MiB\nmax_mutation_size: 32MiB/' conf/cassandra.yaml
  return 0
}

start_log() {   # $1 = label
  mkdir -p "$L"; D=$L/$1
  if [ -e "$D" ] && [ -n "$(ls -A "$D" 2> /dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
  mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
  log "script: $0 $MODE; host: $(hostname); label: $1"
}

# ---------------------------------------------------------------- readings (case 9d)
mx() {   # bean attribute -> a number; `sjk mx -f` takes one attribute per call and each call starts a JVM
  local raw; raw=$(cd "$C" && bin/nodetool sjk mx -mg -b "$1" -f "$2" 2>&1) || { log "sjk failed: $raw"; return 1; }
  echo "$raw" | awk 'NF{l=$0} END{n=split(l,a,/[ \t:=]+/); print a[n]}'
}
num() { [[ "$1" =~ ^[0-9]+$ ]] || fail "not a number: '$1' ($2)"; echo "$1"; }
mem_used()  { num "$(mx "$DIRECT" MemoryUsed)" "direct MemoryUsed"; }
buf_count() { num "$(mx "$DIRECT" Count)" "direct Count"; }
total_hints()    { num "$(mx 'org.apache.cassandra.metrics:type=Storage,name=TotalHints' Count)" TotalHints; }
hints_inprogress(){ num "$(mx 'org.apache.cassandra.db:type=StorageProxy' HintsInProgress)" HintsInProgress; }
nmt_other() { jcmd "$PID" VM.native_memory summary 2> /dev/null | grep 'Other (' | sed -E 's/.*committed=([0-9]+)KB.*/\1/' | head -1; }
# reading <phase> full|light -> a row in readings.csv (epoch ms is taken right after the first call returns)
reading() {
  local phase=$1 kind=$2 ms mem cnt nmt="" tot="" hip=""
  mem=$(mem_used); ms=$(now); cnt=$(buf_count)
  if [ "$kind" = full ]; then nmt=$(nmt_other); tot=$(total_hints); fi
  hip=$(hints_inprogress)
  echo "$phase,$ms,$mem,$cnt,$nmt,$tot,$hip" >> "$D/readings.csv"
  log "reading $phase: MemoryUsed=$mem Count=$cnt NMT_Other_KB=${nmt:-} TotalHints=${tot:-} HintsInProgress=$hip"
  LAST_MEM=$mem; LAST_HIP=$hip
}
# dump <tag> -> full dump on the node, an excerpt in the run folder, counts in summary:
#   parked = threads in take() under switchCurrentBuffer (at most one), blocked = BLOCKED on the pool's monitor there
dump() {
  local f=$D/dump-$1.txt counts
  jcmd "$PID" Thread.print > "$f" 2>&1 || fail "jcmd Thread.print failed"
  counts=$(awk -v RS= '/HintsBufferPool.switchCurrentBuffer/ { if ($0 ~ /LinkedBlockingQueue.take/) t++; else if ($0 ~ /Thread.State: BLOCKED/) b++; else o++ } END {print t+0, b+0, o+0}' "$f")
  awk -v RS= -v ORS='\n\n' '/HintsBufferPool.switchCurrentBuffer/ && (/LinkedBlockingQueue.take/ || !seen++) {print}' "$f" | cut -c1-200 | head -60 > "$D/dump-$1-excerpt.txt"
  note "thread dump $1 at $(now): parked-in-take=$(echo "$counts" | cut -d' ' -f1) blocked-on-monitor=$(echo "$counts" | cut -d' ' -f2) other=$(echo "$counts" | cut -d' ' -f3)  (excerpt: dump-$1-excerpt.txt)"
}
trace_count() { grep -c "$1" "$2" 2> /dev/null || true; }
wait_for() { local d=$1 t=$2 i=0; shift 2
  until "$@"; do sleep 1; i=$((i + 1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s waiting for: $d"; done; log "ok: $d (after ${i}s)"; }
node1_ready() { [ -s "$C/cassandra.pid" ] && [ "$(cd "$C" && bin/nodetool statusbinary 2>&1)" = running ] \
                && (cd "$C" && bin/nodetool status 2>&1 | grep -q "^UN.*$IP1"); }

# ---------------------------------------------------------------- start node 1 (case 9e, step 2)
start_node1() {   # n
  local n=$1
  mkdir -p "$D"
  local opts="-Dcassandra.MAX_HINT_BUFFERS=$n -XX:NativeMemoryTracking=summary -Dstage4.byteman.out=$D/hints-pool.txt -Dstage4.hold.out=$D/hold.txt -Dstage4.hold.ms=$HOLD_MS -javaagent:$BM/byteman-4.0.20.jar=script:$HARNESS/hints-pool.btm,listener:true"
  note "JVM_EXTRA_OPTS=$opts"
  log "+ JVM_EXTRA_OPTS=... bin/cassandra -p cassandra.pid > $D/stdout.txt 2>&1"
  (cd "$C" && JVM_EXTRA_OPTS="$opts" bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1)
  wait_for "node 1 UN and native transport running" 240 node1_ready
  PID=$(cat "$C/cassandra.pid"); note "node 1 pid $PID, up at $(now)"
  # node 1's view of the ring: node 2 must be DN (9d "hints flowing")
  (cd "$C" && bin/nodetool status 2>&1 | grep -E '^(UN|DN)') | tee -a "$S"
  if [ "$MODE" != smoke ]; then check "node 2 ($IP2) is DN on node 1" bash -c "cd '$C' && bin/nodetool status 2>&1 | grep -q '^DN.*$IP2'"; fi
  # 9e step 2: the rules are in place, or an empty trace would mean nothing
  submit -l > "$D/submit-l.txt"; sed 's/^/    | /' "$D/submit-l.txt" | head -40 >&2
  check "Submit -l lists HintsBufferPool.createBuffer()" grep -q 'HintsBufferPool.createBuffer' "$D/submit-l.txt"
  check "Submit -l lists HintsBufferPool.switchCurrentBuffer(" grep -q 'HintsBufferPool.switchCurrentBuffer' "$D/submit-l.txt"
  # 9b "Confirm it took effect"
  jcmd "$PID" VM.system_properties 2> /dev/null | grep 'MAX_HINT_BUFFERS' | tee -a "$S"
  check "the JVM has cassandra.MAX_HINT_BUFFERS=$n" bash -c "jcmd $PID VM.system_properties 2>/dev/null | grep -q 'cassandra.MAX_HINT_BUFFERS=$n\$'"
}

stop_node1() {
  (cd "$C" && bin/nodetool stopdaemon) 2>&1 | tail -1
  for _ in $(seq 60); do daemon_up || break; sleep 1; done
  daemon_up && fail "node 1 did not stop"
  PID=""
}

# ---------------------------------------------------------------- smoke: the helpers, single node
smoke() {
  MODE=smoke; start_log smoke; cd "$C"
  [ -e data ] && fail "data/ exists: smoke would destroy the ring; it is only for a tree without one"
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  ( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "harness copy differs from the committed files"
  mk_yaml 0; git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  check "yaml diff adds 3 lines" test "$(grep -c '^+[^+]' "$D/cassandra.yaml.diff")" -eq 3
  mkdir -p logs; start_node1 3
  log "-- readings"; reading smoke-control full
  check "idle direct MemoryUsed is a positive number" test "$(tail -1 "$D/readings.csv" | cut -d, -f3)" -gt 0
  check "NMT 'Other' is a number" bash -c "tail -1 '$D/readings.csv' | cut -d, -f5 | grep -qE '^[0-9]+\$'"
  log "-- thread dump parse"; dump smoke
  log "-- load and unload the hold"
  submit "$HARNESS/hold-flush.btm" | tee "$D/submit-load.txt"
  submit -l > "$D/submit-l-loaded.txt"; expect "Submit -l shows FlushBufferTask while the hold is loaded" grep -q 'FlushBufferTask' "$D/submit-l-loaded.txt"
  submit -u "$HARNESS/hold-flush.btm" | tee "$D/submit-unload.txt"
  stop_node1
  cp logs/system.log "$D/system.log"; note "ERROR lines in system.log: $(grep -c ' ERROR ' logs/system.log || true)"
  rm -rf data logs cassandra.pid
  note "smoke done; data/ and logs/ removed"
}

# ---------------------------------------------------------------- one capacity value
value() {
  local label=$1 n ARM=0 HOLD=1 BUF=33554432 cores limit thr
  case $label in
    n2|n3|n6)      n=${label#n} ;;
    n3-buf64MiB)   n=3; ARM=1; BUF=67108864 ;;
    n3-natural)    n=3; HOLD=0 ;;
    *) echo "unknown label $label" >&2; exit 2 ;;
  esac
  MODE="value $label"; start_log "$label"; cd "$C"
  cores=$(nproc); limit=$((128 * cores)); thr=$((limit * 75 / 100))
  note "== $label: n=$n bufferSize=$BUF hold=$([ $HOLD = 1 ] && echo "loaded, ${HOLD_MS} ms" || echo none) cores=$cores in-flight-hint limit=$limit (B ends early at $thr); stress n=$ROWS 1KiB x5 columns threads=$THREADS"
  echo "phase,ms,MemoryUsed,Count,NMT_Other_KB,TotalHints,HintsInProgress" > "$D/readings.csv"

  # --- preflight
  check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
  check "node 2 ($IP2:7000) is stopped" bash -c "! nc -z -w 2 $IP2 7000"
  check "ports 7199/9042/9091 free" bash -c '! ss -ltn | grep -q -E ":(7199|9042|9091)\b"'
  check "local disk has >= 20 GB free" test "$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)" -ge 20
  check "the clone is at cassandra-5.0.9" test "$(git describe --tags)" = cassandra-5.0.9
  check "the ring's data is in place (keyspace1)" test -d data/data/keyspace1
  ( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "harness copy differs from the committed files"
  [ "$C" = "$HOME/cassandra-run1" ] || fail "unexpected clone path $C"

  # --- config (9b): the tag's yaml plus the ring edits, plus the two lines of the second-knob arm
  mk_yaml "$ARM"
  git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
  note "yaml diff: $(grep '^[+-][^+-]' "$D/cassandra.yaml.diff" | tr '\n' '|')"
  check "yaml diff adds $((3 + 2 * ARM)) lines" test "$(grep -c '^+[^+]' "$D/cassandra.yaml.diff")" -eq $((3 + 2 * ARM))

  # --- reset (9b): empty the hints directory, move logs/ aside; the ring's data stays
  rm -rf data/hints/* cassandra.pid
  if [ -d logs ] && [ -n "$(ls -A logs)" ]; then run mv logs "$L/logs.before-$label.$(date +%s)"; fi
  mkdir -p logs

  # --- start and control run (9e: steps 2 and "Control run")
  start_node1 "$n"
  local t0; t0=$(now)
  while [ $(($(now) - t0)) -lt 15000 ]; do sleep 1; done          # node up for at least 15 s
  wait_for "the idle flush created the first buffer" 30 grep -q '^created=1 ' "$D/hints-pool.txt"
  reading control full
  expect "exactly one created line at idle, from the hints executor" bash -c "[ \$(grep -c '^created=' '$D/hints-pool.txt') = 1 ] && grep -q '^created=1 .*thread=HintsWriteExecutor' '$D/hints-pool.txt'"

  local STRESS="tools/bin/cassandra-stress write n=$ROWS no-warmup -col size=FIXED(1024) -rate threads=$THREADS -node 127.0.0.1"
  if [ $HOLD = 1 ]; then
    # --- scenario A: load the hold, write until the n-th buffer exists
    note "A: loading the hold at $(now)"
    submit "$HARNESS/hold-flush.btm" | tee "$D/submit-load.txt"
    submit -l > "$D/submit-l-loaded.txt"; check "Submit -l lists the hold rule's trigger (FlushBufferTask)" grep -q 'FlushBufferTask' "$D/submit-l-loaded.txt"
    local a0; a0=$(now); note "A: start at $a0"
    log "+ $STRESS > $D/stress.txt &"; $STRESS > "$D/stress.txt" 2>&1 &
    STRESS_PID=$!
    local waited=0
    until grep -q "^created=$n " "$D/hints-pool.txt"; do
      kill -0 "$STRESS_PID" 2> /dev/null || { tail -3 "$D/stress.txt" >&2; note "A: stress exited before created=$n"; exit 3; }
      sleep 0.5; waited=$((waited + 1)); [ "$waited" -ge $((A_TIMEOUT * 2)) ] && { note "A: no created=$n within ${A_TIMEOUT}s (case 9c: repeat with THREADS=128, then a longer HOLD_MS; record each step as a deviation)"; exit 3; }
    done
    note "A: created=$n seen at $(now) (~$(( $(now) - a0 )) ms after the start)"
    reading A full
  else
    note "natural-load control: the hold is never loaded"
    log "+ $STRESS > $D/stress.txt &"; $STRESS > "$D/stress.txt" 2>&1 &
    STRESS_PID=$!
  fi

  # --- scenario B: keep writing, sample every ~5 s, dump threads at about 10, 30 and 50 s
  local b0 el d10=0 d30=0 d50=0 it0; b0=$(now); note "B: start at $b0"
  while :; do
    it0=$(now); el=$(( (it0 - b0) / 1000 ))
    reading B light
    kill -0 "$STRESS_PID" 2> /dev/null || { note "B: stress exited at ${el}s"; break; }
    [ "$LAST_HIP" -gt "$thr" ] && { note "B: ended early, HintsInProgress $LAST_HIP > 75% of $limit"; break; }
    [ "$el" -ge 10 ] && [ $d10 = 0 ] && { dump B10; d10=1; }
    [ "$el" -ge 30 ] && [ $d30 = 0 ] && { dump B30; d30=1; }
    [ "$el" -ge 50 ] && [ $d50 = 0 ] && { dump B50; d50=1; }
    [ "$el" -ge "$B_SECONDS" ] && { note "B: ${el}s done"; break; }
    local spent=$(( $(now) - it0 )); [ "$spent" -lt 5000 ] && sleep "$(awk -v s="$spent" 'BEGIN{printf "%.1f", (5000-s)/1000}')"
  done
  [ $d10 = 0 ] && [ $d30 = 0 ] && [ $d50 = 0 ] && dump Bend
  reading Bend full

  # --- release the hold; once the writers move again, one more dump and reading (9e step 3)
  if [ $HOLD = 1 ]; then
    local tot0; tot0=$(total_hints); note "release: unloading the hold at $(now), TotalHints $tot0"
    submit -u "$HARNESS/hold-flush.btm" | tee "$D/submit-unload.txt"
    local w=0; until [ "$(total_hints)" -gt "$tot0" ]; do w=$((w + 1)); [ "$w" -ge 40 ] && { note "release: TotalHints did not rise within ~60 s"; break; }; sleep 1; done
    sleep 2; dump release; reading release full
  fi
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2> /dev/null || true; STRESS_PID=""
  grep -E 'Op rate|Total errors|Total partitions|Exception' "$D/stress.txt" | head -5 | tee -a "$S" || true

  # --- stop and read the traces (9e step 4)
  stop_node1
  cp logs/system.log "$D/system.log"
  local created waiting held
  created=$(trace_count '^created=' "$D/hints-pool.txt"); waiting=$(trace_count '^waiting' "$D/hints-pool.txt"); held=$(trace_count '^hold' "$D/hold.txt")
  note "traces: buffers ever created=$created, entries into the disallow branch (waiting)=$waiting, flushes held=$held"
  expect "every created line shows max=$n" bash -c "! grep '^created=' '$D/hints-pool.txt' | grep -qv 'max=$n '"
  expect "every created line shows size=$BUF" bash -c "! grep '^created=' '$D/hints-pool.txt' | grep -qv 'size=$BUF '"
  expect "created never exceeds n ($n)" test "$created" -le "$n"
  note "highest created value: $(grep '^created=' "$D/hints-pool.txt" | sed -E 's/^created=([0-9]+).*/\1/' | sort -n | tail -1)"
  note "peak MemoryUsed in readings.csv: $(tail -n +2 "$D/readings.csv" | cut -d, -f3 | sort -n | tail -1)"
  note "ERROR lines in system.log: $(grep -c ' ERROR ' "$D/system.log" || true); hints directory: $(du -sh data/hints | cut -f1)"
  note "RESULT $label: run finished at $(now)"
}

# ---------------------------------------------------------------- main
case "${1:-}" in
  smoke) smoke ;;
  value) [ -n "${2:-}" ] || { echo "usage: $0 value <n2|n3|n6|n3-buf64MiB|n3-natural>" >&2; exit 2; }; value "$2" ;;
  all)   for v in n2 n3 n6 n3-buf64MiB n3-natural; do ( "$0" value "$v" ) || exit $?; done ;;
  *)     echo "usage: $0 smoke | value <label> | all" >&2; exit 2 ;;
esac
