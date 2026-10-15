#!/usr/bin/env bash
# Unit tier of Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE (case 9c/9e): copies the two harness tests into the clone and runs
# upstream IndexSummaryTest (U0), IndexSummaryCapTest (U1, U2) and IndexSummaryMovedLimitTest (U3), one ant call each.
# usage: unit-run.sh [suffix]   clone: $CASSANDRA_HOME (default ~/cassandra-run3)   output: ~/stage4-logs/imv/unit[-suffix]/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run3}; L=$HOME/stage4-logs/imv/unit${1:+-$1}
mkdir -p "$L"; rm -f "$L/run.out" "$L/summary.txt"
unset CIRCLECI
cp "$H/IndexSummaryCapTest.java" "$H/IndexSummaryMovedLimitTest.java" "$C/test/unit/org/apache/cassandra/io/sstable/indexsummary/"
cd "$C"
echo "clone $C: $(git describe --tags) $(git rev-parse --short HEAD)" | tee "$L/summary.txt"
for t in IndexSummaryTest IndexSummaryCapTest IndexSummaryMovedLimitTest; do
  ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.$t -Dtest.jvm.args="-Dstage4.out=$L/run.out -Dorg.jboss.byteman.contrib.bmunit.agent.port=19091" > "$L/ant-$t.log" 2>&1
  rc=$?
  echo "$t: ant rc=$rc; $(grep -m1 'Tests run' "$L/ant-$t.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant-$t.log") BUILD FAILED" | tee -a "$L/summary.txt"
done
echo "checks: $(grep -c ' check ' "$L/run.out" 2>/dev/null || echo 0); MISMATCH lines: $(grep -c MISMATCH "$L/run.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException' "$L"/ant-*.log | head -5 | tee -a "$L/summary.txt"
