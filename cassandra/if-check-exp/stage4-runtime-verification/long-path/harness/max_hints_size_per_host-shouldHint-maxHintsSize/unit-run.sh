#!/usr/bin/env bash
# Unit tier of max_hints_size_per_host-shouldHint-maxHintsSize (case 9c, 9e unit steps 1-6, amended 2026-10-14).
# usage (on the measured node): unit-run.sh [upstream|harness|instrument|all]     output: ~/stage4-logs/mhs/unit[-instrument]/
#   upstream    StorageProxyTest (testShouldHint, testShouldHintOnExceedingSize with its Byteman stub, ...)
#   harness     ShouldHintSizeTest; STAGE4 lines in harness.out, summary.txt
#   instrument  ShouldHintSizeTest with should-hint.btm attached: decide and flush lines must appear (not a reading)
# Adapted from the repair_session_space harness's unit-run.sh.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
what=${1:-all}
L=$HOME/stage4-logs/mhs/unit; [ "$what" = instrument ] && L=$HOME/stage4-logs/mhs/unit-instrument
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
cp "$H/ShouldHintSizeTest.java" "$C/test/unit/org/apache/cassandra/hints/"
cd "$C"
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) clone $(git describe --tags) $(git rev-parse --short HEAD) harness md5 $(md5sum "$H/ShouldHintSizeTest.java" | cut -c1-12) rules md5 $(md5sum "$H/should-hint.btm" | cut -c1-12)"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  rm -rf build/test/cassandra/hints
  ant testsome -Dtest.name=$cls "$@" > "$L/$(basename ${cls//./_}).ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$(basename ${cls//./_}).ant.log")"
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  run org.apache.cassandra.service.StorageProxyTest
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  rm -f "$L/harness.out"
  run org.apache.cassandra.hints.ShouldHintSizeTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out" 2>/dev/null) MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out" 2>/dev/null)"
  grep 'MISMATCH' "$L/harness.out" 2>/dev/null | tee -a "$S"
  grep '^STAGE4 summary' "$L/harness.out" 2>/dev/null | tee -a "$S"
fi
if [ "$what" = instrument ]; then
  rm -f "$L/harness.out" "$L/mhs.trace"
  run org.apache.cassandra.hints.ShouldHintSizeTest \
    -Dtest.jvm.args="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/should-hint.btm -Dorg.jboss.byteman.verbose=false -Dstage4.trace=$L/mhs.trace -Dstage4.out=$L/harness.out"
  for pat in 'decide ' 'decide .*limit=1048576' 'decide .*result=false' 'decide .*checked=-1' 'flush host=' 'site send'; do say "trace '$pat': $(grep -c "$pat" "$L/mhs.trace" 2>/dev/null)"; done
  grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException' "$L"/*.ant.log | head -5 | tee -a "$S"
fi
