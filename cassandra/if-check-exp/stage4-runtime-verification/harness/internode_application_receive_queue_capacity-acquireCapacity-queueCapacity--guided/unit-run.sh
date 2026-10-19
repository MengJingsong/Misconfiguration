#!/usr/bin/env bash
# Unit tier of internode_application_receive_queue_capacity-acquireCapacity-queueCapacity (case 9c, 9e unit steps 1-6,
# amended 2026-10-14).
# usage (on the measured node): unit-run.sh [upstream|harness|instrument|all]     output: ~/stage4-logs/rqc/unit[-instrument]/
#   upstream    ResourceLimitsTest (the reserve mechanism; the control)
#   harness     AcquireCapacityTest (steps 1-5), then ReceiveQueueWiringTest (step 6) in its own `ant testsome`
#   instrument  AcquireCapacityTest with receive-trace.btm attached: acq lines with cap=1000 and rel lines must appear
# Adapted from the max_hints_size_per_host harness's unit-run.sh.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
what=${1:-all}
L=$HOME/stage4-logs/rqc/unit; [ "$what" = instrument ] && L=$HOME/stage4-logs/rqc/unit-instrument
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
cp "$H/AcquireCapacityTest.java" "$H/ReceiveQueueWiringTest.java" "$C/test/unit/org/apache/cassandra/net/"
cd "$C"
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) clone $(git describe --tags) $(git rev-parse --short HEAD) md5 $(cd "$H" && md5sum AcquireCapacityTest.java ReceiveQueueWiringTest.java receive-trace.btm | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  rm -rf build/test/cassandra
  ant testsome -Dtest.name=$cls "$@" > "$L/$(basename ${cls//./_}).ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$(basename ${cls//./_}).ant.log")"
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  run org.apache.cassandra.net.ResourceLimitsTest
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  rm -f "$L/harness.out"
  run org.apache.cassandra.net.AcquireCapacityTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
  run org.apache.cassandra.net.ReceiveQueueWiringTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out" 2>/dev/null) MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out" 2>/dev/null)"
  grep 'MISMATCH' "$L/harness.out" 2>/dev/null | tee -a "$S"
  grep '^STAGE4 summary\|^STAGE4 note' "$L/harness.out" 2>/dev/null | tee -a "$S"
fi
if [ "$what" = instrument ]; then
  rm -f "$L/harness.out" "$L/rqc.trace"
  run org.apache.cassandra.net.AcquireCapacityTest \
    -Dtest.jvm.args="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/receive-trace.btm -Dorg.jboss.byteman.verbose=false -Dstage4.trace=$L/rqc.trace -Dstage4.out=$L/harness.out"
  for pat in 'acq ' 'acq .*cap=1000 ' 'acq .*out=SUCCESS' 'acq .*out=INSUFFICIENT_GLOBAL' 'acq .*out=INSUFFICIENT_ENDPOINT' 'acq .*gl=300/700' 'rel '; do say "trace '$pat': $(grep -c -- "$pat" "$L/rqc.trace" 2>/dev/null)"; done
  grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException\|ParseException' "$L"/*.ant.log | head -5 | tee -a "$S"
  grep 'MISMATCH' "$L/harness.out" 2>/dev/null | tee -a "$S"
fi
