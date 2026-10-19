#!/usr/bin/env bash
# Stage 4, run 1, unit tier — cdc_total_space-processNewSegment-allowance, case §9e "Unit tier".
#
#   unit-run.sh        ten JVMs, in the §9e order:
#                        1. the upstream CommitLogSegmentManagerCDCTest, unchanged (baseline)
#                        2. CdcTotalSpaceCeilingTest, blocking, S = 32 MiB, at A = 16, 48, 80, 128, 144, 272 MiB
#                        3. the second-knob value, blocking, A = 280 MiB, S = 16 MiB
#                        4. non-blocking, S = 32 MiB, at A = 80 and 144 MiB
#
# Runs on the measured node from a copy of the committed harness (HARNESS, with a SHA256SUMS file made from the
# committed files). Logs every command and its output to ~/stage4-logs/cdc/unit/session.log. One folder per JVM holds
# ant.txt, the JUnit XML, the test's own STAGE4 lines (readings.txt) and, for the harness test, the creation trace
# (cdc-verdict.txt); summary.txt has one line per JVM.
#
# A failing check is a reading, so the script carries on to the next JVM. It stops (exit 3) only when a JVM produced
# no test result at all (a build or set-up failure), and exits 1 at the end if any test failed.
set -uo pipefail

HARNESS=${HARNESS:-$HOME/stage4-harness-run/cdc}
C=$HOME/cassandra-run1
L=$HOME/stage4-logs/cdc/unit
T=test/unit/org/apache/cassandra/db/commitlog
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
run cp "$HARNESS/CdcTotalSpaceCeilingTest.java" "$T/CdcTotalSpaceCeilingTest.java"
cmp "$HARNESS/CdcTotalSpaceCeilingTest.java" "$T/CdcTotalSpaceCeilingTest.java" || fail "the test in the clone differs from the harness copy"
sha256sum "$HARNESS/CdcTotalSpaceCeilingTest.java" "$T/CdcTotalSpaceCeilingTest.java"
log "unit yaml: $(grep -E '^commitlog_segment_size' test/conf/cassandra.yaml)  (the harness sets its own S)"

# ---------------------------------------------------------------- one JVM
ANY_FAILED=0
one_jvm() {
  local label=$1 class=$2 args=$3 d=$L/$1
  mkdir -p "$d"
  args=${args//@D@/$d}
  args=${args//@C@/$C}
  args=${args//@H@/$HARNESS}
  log "=== $label: $class, JVM args: $args"
  rm -f "$C"/build/test/output/TEST-"$class"*.xml
  log "+ ant testsome -Dtest.name=$class -Dtest.jvm.args=\"$args\" > $d/ant.txt"
  ant testsome -Dtest.name="$class" -Dtest.jvm.args="$args" > "$d/ant.txt" 2>&1
  local rc=$?
  log "  rc=$rc ($(wc -l < "$d/ant.txt") lines in $d/ant.txt)"
  grep -E 'Testsuite:.*Tests run:|BUILD|git.sha' "$d/ant.txt" | tee "$d/ant-summary.txt"
  cp "$C"/build/test/output/TEST-"$class"*.xml "$d/junit.xml" 2> /dev/null
  [ -f "$d/readings.txt" ] && { log "test's own readings ($d/readings.txt), without the link events:"; grep -v 'linkEvent' "$d/readings.txt" | sed 's/^/    | /' | cut -c1-330; }
  local line tests failures errors
  line=$(grep -E 'Testsuite:.*Tests run:' "$d/ant.txt" | head -1)
  if [ -z "$line" ]; then echo "$label ant_exit=$rc NO TEST RESULT" | tee -a "$S"; fail "$label produced no test result"; fi
  tests=$(echo "$line"    | sed -E 's/.*Tests run: ([0-9]+).*/\1/')
  failures=$(echo "$line" | sed -E 's/.*Failures: ([0-9]+).*/\1/')
  errors=$(echo "$line"   | sed -E 's/.*Errors: ([0-9]+).*/\1/')
  echo "$label ant_exit=$rc tests=$tests failures=$failures errors=$errors $(grep -h '^ms=[0-9]* RESULT' "$d/readings.txt" 2> /dev/null | sed -E 's/^ms=[0-9]+ //' | cut -c1-200)" | tee -a "$S"
  if [ "$failures" != 0 ] || [ "$errors" != 0 ]; then ANY_FAILED=1; fi
}

harness_jvm() {   # label A S mode
  one_jvm "$1" org.apache.cassandra.db.commitlog.CdcTotalSpaceCeilingTest \
    "-Dstage4.cdc.totalSpaceMiB=$2 -Dstage4.cdc.segmentMiB=$3 -Dstage4.cdc.mode=$4 -Dstage4.unit.out=@D@/readings.txt -javaagent:@C@/build/lib/jars/byteman-4.0.20.jar=script:@H@/cdc-verdict.btm -Dstage4.byteman.out=@D@/cdc-verdict.txt"
}

# ---------------------------------------------------------------- §9e unit tier
one_jvm upstream-baseline org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDCTest ""
for a in 16 48 80 128 144 272; do harness_jvm "u$a" "$a" 32 blocking; done
harness_jvm u280-s16 280 16 blocking
for a in 80 144; do harness_jvm "u$a-nb" "$a" 32 nonblocking; done

log "SUMMARY ($S):"; cat "$S"
if pgrep -f '[C]assandraDaemon' > /dev/null; then log "WARNING: a CassandraDaemon is running"; fi
log "done; any test failed: $ANY_FAILED"
exit "$ANY_FAILED"
