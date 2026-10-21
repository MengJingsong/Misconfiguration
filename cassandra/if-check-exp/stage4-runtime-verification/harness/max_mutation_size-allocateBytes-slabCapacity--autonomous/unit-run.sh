#!/usr/bin/env bash
# Unit tier (B2) of max_mutation_size-allocateBytes-slabCapacity--autonomous (B2a-B2e).
# usage (on the run node): bash unit-run.sh <run>          output: ~/stage4-logs/mss/<run>/unit/
#   1. upstream HintsBufferTest and HintsBufferPoolTest (context: the clone's own tests of the same classes pass)
#   2. the harness SlabCapacityProbeTest; STAGE4 lines in harness.out, summary.txt
# Copies SlabCapacityProbeTest.java into the clone's test/unit/org/apache/cassandra/hints/ (left there, untracked).
# Never run while a node runs from the same clone (ant rebuilds build/). From the max_hints_size_per_host unit-run.sh.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}
RUN=${1:?run name}
L=$HOME/stage4-logs/mss/$RUN/unit
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
if ps -eo cmd | grep -q '[C]assandraDaemon'; then echo "a CassandraDaemon is running; not running ant" | tee -a "$S"; exit 1; fi
cp "$H/SlabCapacityProbeTest.java" "$C/test/unit/org/apache/cassandra/hints/"
cd "$C"
say() { echo "$*" | tee -a "$S"; }
say "unit-run $RUN $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(md5sum "$H/SlabCapacityProbeTest.java" | cut -c1-32) (copied: $(md5sum test/unit/org/apache/cassandra/hints/SlabCapacityProbeTest.java | cut -c1-32))"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  ant testsome -Dtest.name=$cls "$@" > "$L/${cls##*.}.ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/${cls##*.}.ant.log")"
}
run org.apache.cassandra.hints.HintsBufferTest
run org.apache.cassandra.hints.HintsBufferPoolTest
rm -f "$L/harness.out"
run org.apache.cassandra.hints.SlabCapacityProbeTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok ' "$L/harness.out" 2>/dev/null) MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH ' "$L/harness.out" 2>/dev/null)"
grep ' MISMATCH ' "$L/harness.out" 2>/dev/null | tee -a "$S"
grep '^STAGE4 summary' "$L/harness.out" 2>/dev/null | tee -a "$S"
say "unit-run end $(date -Is)"
