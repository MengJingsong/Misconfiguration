#!/usr/bin/env bash
# Unit tier of unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous (B2 as amended 2026-10-26).
# usage (on pc12): unit-run.sh [run-name]     env: CASSANDRA_HOME (default ~/s4-b9-bu-unit), LOGS (default ~/s4-b9-bu-logs)
# Output: $LOGS/<run-name, default run1>/unit/{summary.txt,test.out,ant.log,TEST-*.xml}. Exit 1 if the test fails (a failed first-trigger check is a test failure).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b9-bu-unit}; RUN=${1:-run1}
L=${LOGS:-$HOME/s4-b9-bu-logs}/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum UnloggedBatchWarnTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/UnloggedBatchWarnTest.java" test/unit/org/apache/cassandra/cql3/
rm -f "$L/test.out"; rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.cql3.UnloggedBatchWarnTest -Dtest.jvm.args="-Dstage4.out=$L/test.out" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.cql3.UnloggedBatchWarnTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
grep -h '^STAGE4\|^EXPECTED' "$L/test.out" | tee -a "$S"
say "EXPECTED lines: $(grep -c '^EXPECTED' "$L/test.out") total, $(grep '^EXPECTED' "$L/test.out" | grep -c ' - NO') NO"
[ "$rc" -eq 0 ] || { say "FAIL: ant testsome exit $rc"; exit 1; }
