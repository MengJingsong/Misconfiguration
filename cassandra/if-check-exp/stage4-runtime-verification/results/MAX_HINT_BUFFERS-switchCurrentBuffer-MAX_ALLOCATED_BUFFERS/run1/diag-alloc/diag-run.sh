#!/usr/bin/env bash
# Stage 4, run 1, cluster tier — SUPPLEMENTARY DIAGNOSTIC (results §4.3), written after the five capacity values had run.
# It is not a reading of the case and not one of run 1's values. It asks one question: what allocates the ~9.3 MB of direct
# memory, outside the hints pool, that appears between the idle control and scenario A at every value?
#
# Runs on node 1 (node0, ~/cassandra-run1) with the ring in place and node 2 stopped. n = 3, 32 MiB buffers: the same start,
# the same hold and the same stress as `cluster-run.sh value n3`, plus diag-alloc.btm (one line per ByteBuffer.allocateDirect
# call). It ends after scenario A's readings; scenario B is not run.
#
#   diag-run.sh     -> ~/stage4-logs/hints/cluster/diag-alloc-n3/: session.log, summary.txt, readings.csv, hints-pool.txt, diag-alloc.txt
# Exit codes: 1 a check failed; 3 scenario A never reached created=3. Any non-zero exit stops the stress client and node 1.
# Overridable: THREADS (64), ROWS (200000), HOLD_MS (3000), A_TIMEOUT (180).
set -Eeuo pipefail

C=$HOME/cassandra-run1
HARNESS=$HOME/stage4-harness-run/hints           # the committed harness copy, with SHA256SUMS
DIAG=$HOME/stage4-harness-run/diag               # diag-alloc.btm and its SHA256SUMS
D=$HOME/stage4-logs/hints/cluster/diag-alloc-n3
BM=$C/build/lib/jars
IP1=198.22.255.77; IP2=198.22.255.91
N=3
THREADS=${THREADS:-64}; ROWS=${ROWS:-200000}; HOLD_MS=${HOLD_MS:-3000}; A_TIMEOUT=${A_TIMEOUT:-180}
DIRECT='java.nio:type=BufferPool,name=direct'
S=""; PID=""; STRESS_PID=""

log()  { echo "[$(date '+%F %T')] $*" >&2; }
note() { printf '%s\n' "$*" | tee -a "$S"; }
fail() { log "FAIL: $*"; exit 1; }
now()  { date +%s%3N; }
check(){ local d=$1; shift; if "$@"; then log "CHECK PASS: $d"; else fail "CHECK FAILED: $d"; fi; }
daemon_up() { pgrep -f '[o]rg.apache.cassandra.service.CassandraDaemon' > /dev/null; }
submit() { (cd "$C" && java -cp "$BM/byteman-submit-4.0.20.jar" org.jboss.byteman.agent.submit.Submit "$@" 2>&1); }

cleanup() {
  local rc=$?; trap - EXIT ERR
  [ "$rc" -ne 0 ] && log "EXIT rc=$rc: stopping stress and node 1"
  pkill -f '[o]rg.apache.cassandra.stress.Stress' 2> /dev/null || true
  if daemon_up; then (cd "$C" && bin/nodetool stopdaemon) > /dev/null 2>&1 || true
    for _ in $(seq 60); do daemon_up || break; sleep 1; done; fi
  daemon_up && log "WARNING: a CassandraDaemon is still running"
  sleep 1; exit "$rc"
}
trap 'log "ERR line $LINENO: $BASH_COMMAND"' ERR
trap cleanup EXIT

mx() {
  local raw; raw=$(cd "$C" && bin/nodetool sjk mx -mg -b "$1" -f "$2" 2>&1) || { log "sjk failed: $raw"; return 1; }
  echo "$raw" | awk 'NF{l=$0} END{n=split(l,a,/[ \t:=]+/); print a[n]}'
}
num() { [[ "$1" =~ ^[0-9]+$ ]] || fail "not a number: '$1' ($2)"; echo "$1"; }
nmt_other() { jcmd "$PID" VM.native_memory summary 2> /dev/null | grep 'Other (' | sed -E 's/.*committed=([0-9]+)KB.*/\1/' | head -1; }
reading() {   # <phase> full|light -> a row in readings.csv (epoch ms is taken right after the MemoryUsed call returns)
  local phase=$1 kind=$2 ms mem cnt nmt="" tot=""
  mem=$(num "$(mx "$DIRECT" MemoryUsed)" MemoryUsed); ms=$(now); cnt=$(num "$(mx "$DIRECT" Count)" Count)
  if [ "$kind" = full ]; then nmt=$(nmt_other); tot=$(num "$(mx 'org.apache.cassandra.metrics:type=Storage,name=TotalHints' Count)" TotalHints); fi
  echo "$phase,$ms,$mem,$cnt,$nmt,$tot" >> "$D/readings.csv"
  log "reading $phase: MemoryUsed=$mem Count=$cnt NMT_Other_KB=${nmt:-} TotalHints=${tot:-}"
}
wait_for() { local d=$1 t=$2 i=0; shift 2
  until "$@"; do sleep 1; i=$((i + 1)); [ "$i" -ge "$t" ] && fail "timeout ${t}s waiting for: $d"; done; log "ok: $d (after ${i}s)"; }
node1_ready() { daemon_up || fail "node 1 exited during start (see $D/stdout.txt)"; [ -s "$C/cassandra.pid" ] && [ "$(cd "$C" && bin/nodetool statusbinary 2>&1)" = running ] \
                && (cd "$C" && bin/nodetool status 2>&1 | grep -q "^UN.*$IP1"); }

# ---- set up
mkdir -p "$(dirname "$D")"
if [ -e "$D" ] && [ -n "$(ls -A "$D" 2> /dev/null)" ]; then mv "$D" "$D.attempt-$(date +%s)"; fi
mkdir -p "$D"; S=$D/summary.txt; exec > >(tee -a "$D/session.log") 2>&1
log "script: $0; host: $(hostname)"; cd "$C"

check "no CassandraDaemon running" bash -c '! pgrep -f "[o]rg.apache.cassandra.service.CassandraDaemon" >/dev/null'
check "node 2 ($IP2:7000) is stopped" bash -c "! nc -z -w 2 $IP2 7000"
check "ports 7199/9042/9091 free" bash -c '! ss -ltn | grep -q -E ":(7199|9042|9091)\b"'
check "the clone is at cassandra-5.0.9" test "$(git describe --tags)" = cassandra-5.0.9
check "the ring's data is in place (keyspace1)" test -d data/data/keyspace1
( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "harness copy differs from the committed files"
( cd "$DIAG" && sha256sum -c SHA256SUMS ) || fail "diagnostic rule differs from the committed file"

# the tag's yaml plus the three ring edits, exactly as cluster-run.sh builds it for n = 3
git show HEAD:conf/cassandra.yaml > conf/cassandra.yaml
sed -i -e "s/^cluster_name: 'Test Cluster'/cluster_name: 'stage4-hints'/" \
       -e "s/^      - seeds: \"127.0.0.1:7000\"/      - seeds: \"$IP1:7000\"/" \
       -e "s/^listen_address: localhost/listen_address: $IP1/" conf/cassandra.yaml
git diff -U0 conf/cassandra.yaml > "$D/cassandra.yaml.diff"
check "yaml diff adds 3 lines" test "$(grep -c '^+[^+]' "$D/cassandra.yaml.diff")" -eq 3

rm -rf data/hints/* cassandra.pid
if [ -d logs ] && [ -n "$(ls -A logs)" ]; then mv logs "$(dirname "$D")/logs.before-diag-alloc-n3.$(date +%s)"; fi
mkdir -p logs
echo "phase,ms,MemoryUsed,Count,NMT_Other_KB,TotalHints" > "$D/readings.csv"

# ---- start node 1: the same options as cluster-run.sh value n3, plus the diagnostic rule and its output file.
# The rule is on a JDK class, so Byteman's own jar must also be on the bootstrap class path (boot:); the first attempt without it
# died in startup with NoClassDefFoundError: org/jboss/byteman/rule/exception/EarlyReturnException (results §4.3).
opts="-Dcassandra.MAX_HINT_BUFFERS=$N -XX:NativeMemoryTracking=summary -Dstage4.byteman.out=$D/hints-pool.txt -Dstage4.hold.out=$D/hold.txt -Dstage4.hold.ms=$HOLD_MS -Dstage4.diag.out=$D/diag-alloc.txt -javaagent:$BM/byteman-4.0.20.jar=boot:$BM/byteman-4.0.20.jar,script:$HARNESS/hints-pool.btm,script:$DIAG/diag-alloc.btm,listener:true"
note "== diagnostic, n=$N bufferSize=33554432 hold=loaded, ${HOLD_MS} ms; stress n=$ROWS threads=$THREADS"
note "JVM_EXTRA_OPTS=$opts"
(JVM_EXTRA_OPTS="$opts" bin/cassandra -p cassandra.pid > "$D/stdout.txt" 2>&1)
wait_for "node 1 UN and native transport running" 240 node1_ready
PID=$(cat cassandra.pid); note "node 1 pid $PID, up at $(now)"
check "node 2 ($IP2) is DN on node 1" bash -c "bin/nodetool status 2>&1 | grep -q '^DN.*$IP2'"
submit -l > "$D/submit-l.txt"
check "Submit -l lists HintsBufferPool.createBuffer()" grep -q 'HintsBufferPool.createBuffer' "$D/submit-l.txt"
check "Submit -l lists the diagnostic rule (allocateDirect)" grep -q 'allocateDirect' "$D/submit-l.txt"
check "the JVM has cassandra.MAX_HINT_BUFFERS=$N" bash -c "jcmd $PID VM.system_properties 2>/dev/null | grep -q 'cassandra.MAX_HINT_BUFFERS=$N\$'"

# ---- the control run: up at least 15 s, no writes
t0=$(now); while [ $(($(now) - t0)) -lt 15000 ]; do sleep 1; done
wait_for "the idle flush created the first buffer" 30 grep -q '^created=1 ' "$D/hints-pool.txt"
reading control full

# ---- scenario A: load the hold, write until the n-th buffer exists; light readings while waiting
STRESS="tools/bin/cassandra-stress write n=$ROWS no-warmup -col size=FIXED(1024) -rate threads=$THREADS -node 127.0.0.1"
note "A: loading the hold at $(now)"
submit "$HARNESS/hold-flush.btm" | tee "$D/submit-load.txt"
a0=$(now); note "A: start at $a0"
log "+ $STRESS > $D/stress.txt &"; $STRESS > "$D/stress.txt" 2>&1 &
STRESS_PID=$!
waited=0
until grep -q "^created=$N " "$D/hints-pool.txt"; do
  kill -0 "$STRESS_PID" 2> /dev/null || { tail -3 "$D/stress.txt" >&2; note "A: stress exited before created=$N"; exit 3; }
  sleep 0.5; waited=$((waited + 1)); [ "$waited" -ge $((A_TIMEOUT * 2)) ] && { note "A: no created=$N within ${A_TIMEOUT}s"; exit 3; }
  [ $((waited % 4)) -eq 0 ] && reading during light
done
note "A: created=$N seen at $(now) (~$(( $(now) - a0 )) ms after the start)"
reading A full
sleep 3; reading A-plus3s light

# ---- end: stop the stress, release the hold, stop node 1, keep the traces
pkill -f '[o]rg.apache.cassandra.stress.Stress' 2> /dev/null || true; STRESS_PID=""
submit -u "$HARNESS/hold-flush.btm" | tee "$D/submit-unload.txt"
(cd "$C" && bin/nodetool stopdaemon) 2>&1 | tail -1
for _ in $(seq 90); do daemon_up || break; sleep 1; done
daemon_up && fail "node 1 did not stop"
PID=""
cp logs/system.log "$D/system.log"
note "traces: created lines=$(grep -c '^created=' "$D/hints-pool.txt"), diag-alloc lines=$(grep -c '^alloc ' "$D/diag-alloc.txt"), diag-alloc bytes=$(stat -c %s "$D/diag-alloc.txt")"
note "ERROR lines in system.log: $(grep -c ' ERROR ' "$D/system.log" || true)"
note "RESULT diagnostic: finished at $(now)"
