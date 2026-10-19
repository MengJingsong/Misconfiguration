#!/usr/bin/env bash
# Unit tier of native_transport_receive_queue_capacity-acquireCapacity-queueCapacity (case 9e unit steps u0-u6, amended
# 2026-10-15).
# usage (on the measured node): unit-run.sh [upstream|harness|instrument|all]     output: ~/stage4-logs/ntq/<run>/unit[-instrument]/
#   upstream    ClientResourceLimitsTest (the reserves and both modes; the control)
#   harness     NativeQueueModesTest (u0-u6) with unit-hold.btm (the gate)
#   instrument  NativeQueueModesTest with unit-hold.btm and ntq-trace.btm: every trace line kind must appear
# NTQ_RUN names the run folder (default run1). Adapted from the internode_application_receive_queue_capacity unit-run.sh.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
what=${1:-all}; RUN=${NTQ_RUN:-run1}
L=$HOME/stage4-logs/ntq/$RUN/unit; [ "$what" = instrument ] && L=$HOME/stage4-logs/ntq/$RUN/unit-instrument
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
cp "$H/NativeQueueModesTest.java" "$C/test/unit/org/apache/cassandra/transport/"
cd "$C"
BM=$C/build/lib/jars/byteman-4.0.20.jar
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) clone $(git describe --tags) $(git rev-parse --short HEAD) md5 $(cd "$H" && md5sum NativeQueueModesTest.java unit-hold.btm ntq-trace.btm | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  rm -rf build/test/cassandra
  ant testsome -Dtest.name=$cls "$@" > "$L/$(basename ${cls//./_}).ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$(basename ${cls//./_}).ant.log")"
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  run org.apache.cassandra.transport.ClientResourceLimitsTest
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  rm -f "$L/harness.out"
  run org.apache.cassandra.transport.NativeQueueModesTest \
    -Dtest.jvm.args="-javaagent:$BM=script:$H/unit-hold.btm -Dorg.jboss.byteman.verbose=false -Dstage4.out=$L/harness.out"
fi
if [ "$what" = instrument ]; then
  rm -f "$L/harness.out" "$L/ntq.trace"
  run org.apache.cassandra.transport.NativeQueueModesTest \
    -Dtest.jvm.args="-javaagent:$BM=script:$H/unit-hold.btm,script:$H/ntq-trace.btm -Dorg.jboss.byteman.verbose=false -Dstage4.trace=$L/ntq.trace -Dstage4.out=$L/harness.out"
  for pat in '^new ' '^new .*cap=123456 ' '^new .*throw=true' '^acq ' '^acq .*out=SUCCESS' '^acq .*out=INSUFFICIENT_GLOBAL' '^rel ' '^dec ' '^dec .*bp=BYTES_IN_FLIGHT' '^rls ' '^disc ' '^ldisc ' '^wake '; do say "trace '$pat': $(grep -c -- "$pat" "$L/ntq.trace" 2>/dev/null)"; done
  grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException\|ParseException' "$L"/*.ant.log | head -5 | tee -a "$S"
fi
if [ -f "$L/harness.out" ]; then
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out") MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out")"
  grep 'MISMATCH' "$L/harness.out" | tee -a "$S"
  grep '^STAGE4 summary\|^STAGE4 note' "$L/harness.out" | tee -a "$S"
fi
