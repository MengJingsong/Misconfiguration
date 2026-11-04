#!/usr/bin/env bash
# Unit tier of SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS (case 9e unit steps U1-U5,
# amended 2026-10-15). Adapted from the native_transport_receive_queue_capacity unit-run.sh.
# usage (on the measured node): unit-run.sh [upstream|harness|all]      output: ~/stage4-logs/mmk/<run>/unit/
#   upstream   VectorTypeTest (whole class, parameterized); the control is its testTooManyMaterializedKeys (refusal at L = 10, row count)
#   harness    MaterializedKeysLimitTest with unit-trace.btm
# MMK_RUN names the run folder (default run1).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
what=${1:-all}; RUN=${MMK_RUN:-run1}
L=$HOME/stage4-logs/mmk/$RUN/unit
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
cp "$H/MaterializedKeysLimitTest.java" "$C/test/unit/org/apache/cassandra/index/sai/cql/"
cd "$C"
BM=$C/build/lib/jars/byteman-4.0.20.jar
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) clone $(git describe --tags) $(git rev-parse --short HEAD) md5 $(cd "$H" && md5sum MaterializedKeysLimitTest.java unit-trace.btm | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  rm -rf build/test/cassandra
  ant testsome -Dtest.name=$cls "$@" > "$L/$(basename ${cls//./_}).ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$(basename ${cls//./_}).ant.log")"
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  # VectorTypeTest is parameterized (VectorTester), so -Dtest.methods matches nothing (shakedown 1): run the class, read the method
  run org.apache.cassandra.index.sai.cql.VectorTypeTest
  for x in "$L"/TEST-org.apache.cassandra.index.sai.cql.VectorTypeTest*.xml; do
    say "upstream testTooManyMaterializedKeys: $(grep -o '<testcase [^>]*name="testTooManyMaterializedKeys[^"]*"[^>]*\(/>\|>\)' "$x" | sed 's/classname="[^"]*" //' | tr '\n' ' ') failures-in-it: $(awk '/name="testTooManyMaterializedKeys/{f=1} f&&/<(failure|error)/{n++} f&&/<\/testcase>|\/>$/{f=0} END{print n+0}' "$x")"
  done
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  rm -f "$L/harness.out"
  run org.apache.cassandra.index.sai.cql.MaterializedKeysLimitTest \
    -Dtest.jvm.args="-javaagent:$BM=script:$H/unit-trace.btm -Dorg.jboss.byteman.verbose=false -Dstage4.out=$L/harness.out"
  grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException\|ParseException' "$L"/*.ant.log | head -5 | tee -a "$S"
fi
if [ -f "$L/harness.out" ]; then
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out") MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out")"
  grep 'MISMATCH' "$L/harness.out" | tee -a "$S"
  grep '^STAGE4 summary\|^STAGE4 deep\|^STAGE4 start' "$L/harness.out" | tee -a "$S"
fi
