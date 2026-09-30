#!/usr/bin/env bash
# Stage 4 instrument check — hold-flush.btm.
# Case §9e, step 2 ("Submit -l" lists the trace rules) and step 3 ("Instrument check, hold rule").
# A check of the instruments, not a reading of the case (results §1.2).
#
# Driven from the workstation: node 1 = NODE0 (the measured node), node 2 = NODE1 (the hint target,
# environment.md §5). Steps:
#   A  ring first-time step: both nodes up, keyspace1 RF = 2, stress table, node 2 stopped, node 1 stopped
#   B  start node 1 alone with hints-pool.btm (n = 3), `Submit -l` must list both trace rules
#   C  load hold-flush.btm; write 10,000 rows (about 52 MB, more than one 32 MiB buffer);
#      a thread dump must catch the hints writer inside FlushBufferTask.run while it is held
#   D  expect at least one `hold` line, `created=2`, and one held flush per flush-count line
#   E  unload the rule; write 6,000 more rows; a new flush must happen (flush-count) with no new `hold` line
#      (not `created=3`: the pool reuses a recycled buffer before it creates one, so a third buffer never appears)
#      flush-count.btm, a throwaway rule next to this script, counts every FlushBufferTask.run entry
#   F  stop everything and remove data/ and logs/ on both nodes (the first run repeats step A itself)
# Output: $OUT (default ./hold-check-out): session.log and the node-side files.
set -uo pipefail
N0=${N0:-jason92@pc66.cloudlab.umass.edu}
N1=${N1:-jason92@pc80.cloudlab.umass.edu}
OUT=${OUT:-$PWD/hold-check-out}
mkdir -p "$OUT"
exec > >(tee "$OUT/session.log") 2>&1

C='$HOME/cassandra-run1'                      # expanded on the node
C2='$HOME/cassandra-node2'
H='$HOME/stage4-harness-run/hints'            # committed harness copy on node 1
T='$HOME/stage4-logs/hints/hold-check'        # node-side output
IP0=198.22.255.77

log()   { echo "[$(date '+%F %T')] $*"; }
r0()    { ssh -o BatchMode=yes -n "$N0" "$@"; }
r1()    { ssh -o BatchMode=yes -n "$N1" "$@"; }
FAILS=0
check() { if [ "$1" = 0 ]; then log "CHECK PASS: $2"; else log "CHECK FAIL: $2"; FAILS=$((FAILS + 1)); fi; }
stop_all() {
  r0 "cd $C && (pgrep -f '[C]assandraDaemon' > /dev/null && bin/nodetool stopdaemon > /dev/null 2>&1; true)"
  r1 "cd $C2 && (pgrep -f '[C]assandraDaemon' > /dev/null && bin/nodetool stopdaemon > /dev/null 2>&1; true)"
  for i in $(seq 1 30); do
    if ! r0 "pgrep -f '[C]assandraDaemon'" > /dev/null && ! r1 "pgrep -f '[C]assandraDaemon'" > /dev/null; then return 0; fi
    sleep 2
  done
  log "WARNING: a CassandraDaemon is still running"; return 1
}
wait_node1() {   # UN for node 1 and the native transport running
  for i in $(seq 1 60); do
    if [ "$(r0 "cd $C && bin/nodetool statusbinary 2>&1")" = running ] \
       && r0 "cd $C && bin/nodetool status 2>&1 | grep -q '^UN.*$IP0'"; then log "node 1 up and native transport running (~$((i * 3)) s)"; return 0; fi
    sleep 3
  done; return 1
}
cleanup() {
  log "== F: cleanup"
  stop_all
  r0 "cd $C && cp logs/system.log $T/node1-system.log 2>/dev/null; rm -rf data logs cassandra.pid"
  r1 "cd $C2 && rm -rf data logs cassandra.pid"
  r0 "cd $T && tar cf - *.txt" 2> /dev/null | tar xf - -C "$OUT"
  log "both nodes stopped; data/ and logs/ removed; node-side files copied to $OUT"
  log "RESULT: $([ "$FAILS" = 0 ] && echo 'all checks passed' || echo "$FAILS check(s) failed")"
}

log "script: $0; node 1 $N0, node 2 $N1"
r0 "pgrep -f '[C]assandraDaemon'" > /dev/null && { log "FAIL: a daemon is running on node 1"; FAILS=1; exit 1; }
r1 "pgrep -f '[C]assandraDaemon'" > /dev/null && { log "FAIL: a daemon is running on node 2"; FAILS=1; exit 1; }
r0 "rm -rf $T && mkdir -p $T && cd $H && sha256sum -c SHA256SUMS" ; check $? "node 1's harness copy equals the committed files"
trap cleanup EXIT   # armed only after the pre-checks, so a refusal never touches a running node

# ---------------------------------------------------------------- A
log "== A: ring first-time step"
r0 "cd $C && bin/cassandra -p cassandra.pid > $T/node1-first-stdout.txt 2>&1"
r1 "cd $C2 && bin/cassandra -p cassandra.pid > \$HOME/stage4-logs/second-node/node2-hold-check-stdout.txt 2>&1"
for i in $(seq 1 60); do
  [ "$(r0 "cd $C && bin/nodetool status 2>&1 | grep -c '^UN'")" = 2 ] && [ "$(r0 "cd $C && bin/nodetool statusbinary 2>&1")" = running ] && { log "ring has 2 UN (~$((i * 5)) s)"; break; }
  sleep 5
done
r0 "cd $C && bin/cqlsh -e \"CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};\""
r0 "cd $C && tools/bin/cassandra-stress write n=1000 no-warmup -node 127.0.0.1 2>&1 | grep -E 'Total errors|Op rate'"
r1 "cd $C2 && bin/nodetool stopdaemon 2>&1 | tail -1"
for i in $(seq 1 30); do r0 "cd $C && bin/nodetool status 2>&1 | grep -q '^DN'" && { log "node 1 sees node 2 as DN (~$((i * 4)) s)"; break; }; sleep 4; done
r0 "cd $C && bin/nodetool stopdaemon 2>&1 | tail -1"
for i in $(seq 1 30); do r0 "pgrep -f '[C]assandraDaemon'" > /dev/null || break; sleep 2; done

# ---------------------------------------------------------------- B
log "== B: node 1 alone, with hints-pool.btm (n = 3)"
r0 "cd $C && JVM_EXTRA_OPTS=\"-Dcassandra.MAX_HINT_BUFFERS=3 -XX:NativeMemoryTracking=summary -Dstage4.byteman.out=$T/hints-pool.txt -Dstage4.hold.out=$T/hold.txt -Dstage4.hold.ms=3000 -Dstage4.flush.out=$T/flush-count.txt -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/hints-pool.btm,listener:true\" bin/cassandra -p cassandra.pid > $T/node1-stdout.txt 2>&1"
wait_node1; check $? "node 1 started with the agent"
r0 "cd $C && bin/nodetool status 2>&1 | grep -E '^(UN|DN)'"
r0 "cd $C && java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l > $T/submit-l-start.txt 2>&1; cat $T/submit-l-start.txt"
r0 "grep -q 'createBuffer' $T/submit-l-start.txt && grep -q 'switchCurrentBuffer' $T/submit-l-start.txt"; check $? "Submit -l lists triggers on HintsBufferPool.createBuffer() and switchCurrentBuffer()"
sleep 15   # the periodic flush (hints_flush_period 10 s) creates the first buffer on an idle node
r0 "cat $T/hints-pool.txt"

# ---------------------------------------------------------------- C
log "== C: load hold-flush.btm, write 10,000 rows, catch the hints writer held"
ssh -o BatchMode=yes "$N0" "cat > $T/flush-count.btm" < "$(dirname "$0")/flush-count.btm"
r0 "cd $C && java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit $T/flush-count.btm 2>&1 | tee $T/submit-load-count.txt"
r0 "cd $C && java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit $H/hold-flush.btm 2>&1 | tee $T/submit-load.txt"
r0 "cd $C && java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l > $T/submit-l-loaded.txt 2>&1; grep -c FlushBufferTask $T/submit-l-loaded.txt"
ssh -o BatchMode=yes "$N0" "C=$C T=$T bash -s" <<'EOS'
cd "$C"
PID=$(cat cassandra.pid)
( tools/bin/cassandra-stress write n=10000 no-warmup -col 'size=FIXED(1024)' -node 127.0.0.1 > "$T/stress-held.txt" 2>&1 & )
found=0
for i in $(seq 1 80); do
  jcmd "$PID" Thread.print > "$T/dump.txt" 2>/dev/null
  awk '/^"HintsWriteExecutor/{f=1} f&&/^$/{exit} f' "$T/dump.txt" > "$T/dump-hintswriter.txt"
  if grep -q 'FlushBufferTask.run' "$T/dump-hintswriter.txt"; then found=1; cp "$T/dump-hintswriter.txt" "$T/dump-hintswriter-held.txt"; break; fi
  sleep 0.25
done
echo "hints writer caught inside FlushBufferTask.run: found=$found (poll $i)"
cat "$T/dump-hintswriter-held.txt" 2>/dev/null | head -12
for i in $(seq 1 40); do grep -q 'END' "$T/stress-held.txt" && break; sleep 1; done
grep -E 'Op rate|Total errors' "$T/stress-held.txt"
EOS
r0 "grep -q 'FlushBufferTask.run' $T/dump-hintswriter-held.txt"; check $? "a thread dump caught the hints writer inside FlushBufferTask.run (held)"

# ---------------------------------------------------------------- D
log "== D: trace lines after the held write"
sleep 6
r0 "echo '-- hints-pool.txt'; cat $T/hints-pool.txt; echo '-- hold.txt'; cat $T/hold.txt"
r0 "test \$(grep -c '^hold' $T/hold.txt) -ge 1"; check $? "at least one hold line (delay=3000)"
r0 "grep -q '^created=2 ' $T/hints-pool.txt"; check $? "created=2 is in the trace"
HOLDS1=$(r0 "grep -c '^hold' $T/hold.txt"); FLUSH1=$(r0 "grep -c '^flush' $T/flush-count.txt"); log "hold lines so far: $HOLDS1; flushes so far: $FLUSH1"
r0 "echo '-- flush-count.txt'; cat $T/flush-count.txt"
[ "$HOLDS1" = "$FLUSH1" ] && [ "$FLUSH1" -ge 1 ]; check $? "while the rule was loaded every flush was held (flush lines = hold lines, at least one)"

# ---------------------------------------------------------------- E
log "== E: unload the rule, write 6,000 more rows; a flush must happen and must not be held"
r0 "cd $C && java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -u $H/hold-flush.btm 2>&1 | tee $T/submit-unload.txt"
r0 "cd $C && tools/bin/cassandra-stress write n=6000 no-warmup -col 'size=FIXED(1024)' -node 127.0.0.1 2>&1 | grep -E 'Op rate|Total errors'"
sleep 8
r0 "echo '-- hints-pool.txt'; cat $T/hints-pool.txt"
HOLDS2=$(r0 "grep -c '^hold' $T/hold.txt"); log "hold lines after the unload: $HOLDS2"
FLUSH2=$(r0 "grep -c '^flush' $T/flush-count.txt"); log "flushes after the unload: $FLUSH2"
r0 "echo '-- flush-count.txt'; cat $T/flush-count.txt"
[ "$FLUSH2" -gt "$FLUSH1" ]; check $? "a new flush happened after the unload"
[ "$HOLDS1" = "$HOLDS2" ]; check $? "and it was not held: no new hold line"
r0 "cd $C && grep -c ' ERROR ' logs/system.log" || true
log "== done; cleanup follows"
