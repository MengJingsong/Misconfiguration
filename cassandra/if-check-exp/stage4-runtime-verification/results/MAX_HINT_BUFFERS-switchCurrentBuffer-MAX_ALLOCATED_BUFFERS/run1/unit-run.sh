#!/usr/bin/env bash
# Stage 4, run 1, unit tier — MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS, case §9e "Unit tier".
#
#   unit-run.sh        seven JVMs, one per value, in the §9e order:
#                        1. upstream HintsBufferPoolTest at n = 2, 3, 6
#                        2. HintsPoolCeilingTest at n = 2, 3, 6 with 1 MiB buffers, then n = 3 with 2 MiB
#
# Runs on node0 from a copy of the committed harness (HARNESS, with a SHA256SUMS file made from the
# committed files). Logs every command and its output to ~/stage4-logs/hints/unit/session.log. One folder
# per JVM holds ant.txt, the JUnit XML and, for the harness test, the test's own STAGE4 lines; summary.txt
# has one line per JVM.
#
# A failing assertion is a reading, so the script carries on to the next JVM. It stops (exit 3) only when a
# JVM produced no test result at all (a build or set-up failure), and exits 1 at the end if any test failed.
set -uo pipefail

HARNESS=${HARNESS:-$HOME/stage4-harness-run/hints}
C=$HOME/cassandra-run1
L=$HOME/stage4-logs/hints/unit
T=test/unit/org/apache/cassandra/hints
S=$L/summary.txt

if [ -e "$L" ]; then mv "$L" "$L.attempt-$(date +%s)"; fi   # keep an earlier attempt, start clean
mkdir -p "$L"
exec > >(tee -a "$L/session.log") 2>&1

log()  { echo "[$(date '+%F %T')] $*"; }
run()  { log "+ $*"; "$@"; local rc=$?; log "  rc=$rc"; return $rc; }
fail() { log "FAIL: $*"; exit 3; }

log "script: $0"
log "host: $(hostname); kernel: $(uname -r); cores: $(nproc)"
run java -version
run ant -version

# ---------------------------------------------------------------- set-up checks
cd "$C" || fail "no clone at $C"
log "clone HEAD: $(git rev-parse HEAD); describe: $(git describe --tags)"
log "clone status:"; git status --short
[ "$(git describe --tags)" = cassandra-5.0.9 ] || fail "the clone is not at cassandra-5.0.9"
if pgrep -f '[C]assandraDaemon' > /dev/null; then fail "a CassandraDaemon is running"; fi
log "harness copy: $HARNESS"
( cd "$HARNESS" && sha256sum -c SHA256SUMS ) || fail "the harness copy differs from the committed files"
run cp "$HARNESS/HintsPoolCeilingTest.java" "$T/HintsPoolCeilingTest.java"
cmp "$HARNESS/HintsPoolCeilingTest.java" "$T/HintsPoolCeilingTest.java" || fail "the test in the clone differs from the harness copy"
sha256sum "$HARNESS/HintsPoolCeilingTest.java" "$T/HintsPoolCeilingTest.java"

# ---------------------------------------------------------------- one JVM
ANY_FAILED=0
one_jvm() {
  local label=$1 class=$2 args=$3 d=$L/$1
  mkdir -p "$d"
  args=${args//@D@/$d}
  log "=== $label: $class, JVM args: $args"
  rm -f "$C"/build/test/output/TEST-"$class"*.xml
  log "+ ant testsome -Dtest.name=$class -Dtest.jvm.args=\"$args\" > $d/ant.txt"
  ant testsome -Dtest.name="$class" -Dtest.jvm.args="$args" > "$d/ant.txt" 2>&1
  local rc=$?
  log "  rc=$rc ($(wc -l < "$d/ant.txt") lines in $d/ant.txt)"
  grep -E 'Testsuite:.*Tests run:|BUILD|git.sha' "$d/ant.txt" | tee "$d/ant-summary.txt"
  cp "$C"/build/test/output/TEST-"$class"*.xml "$d/junit.xml" 2> /dev/null
  [ -f "$d/stage4.txt" ] && { log "test's own readings ($d/stage4.txt):"; sed 's/^/    | /' "$d/stage4.txt"; }
  local line tests failures errors
  line=$(grep -E 'Testsuite:.*Tests run:' "$d/ant.txt" | head -1)
  if [ -z "$line" ]; then echo "$label ant_exit=$rc NO TEST RESULT" | tee -a "$S"; fail "$label produced no test result"; fi
  tests=$(echo "$line"    | sed -E 's/.*Tests run: ([0-9]+).*/\1/')
  failures=$(echo "$line" | sed -E 's/.*Failures: ([0-9]+).*/\1/')
  errors=$(echo "$line"   | sed -E 's/.*Errors: ([0-9]+).*/\1/')
  echo "$label ant_exit=$rc tests=$tests failures=$failures errors=$errors" | tee -a "$S"
  if [ "$failures" != 0 ] || [ "$errors" != 0 ]; then ANY_FAILED=1; fi
}

# ---------------------------------------------------------------- §9e unit tier
# 1. upstream test at each n
for n in 2 3 6; do
  one_jvm "upstream-n$n" org.apache.cassandra.hints.HintsBufferPoolTest "-Dcassandra.MAX_HINT_BUFFERS=$n"
done
# 2. harness test: n = 2, 3, 6 with 1 MiB buffers, then n = 3 with 2 MiB (3 x 2 MiB = 6 x 1 MiB, the second-knob check)
for n in 2 3 6; do
  one_jvm "ceiling-n$n-1MiB" org.apache.cassandra.hints.HintsPoolCeilingTest \
    "-Dcassandra.MAX_HINT_BUFFERS=$n -Dstage4.hints.bufferSize=1048576 -Dstage4.unit.out=@D@/stage4.txt"
done
one_jvm "ceiling-n3-2MiB" org.apache.cassandra.hints.HintsPoolCeilingTest \
  "-Dcassandra.MAX_HINT_BUFFERS=3 -Dstage4.hints.bufferSize=2097152 -Dstage4.unit.out=@D@/stage4.txt"

log "SUMMARY ($S):"; cat "$S"
if pgrep -f '[C]assandraDaemon' > /dev/null; then log "WARNING: a CassandraDaemon is running"; fi
log "done; any test failed: $ANY_FAILED"
exit "$ANY_FAILED"
