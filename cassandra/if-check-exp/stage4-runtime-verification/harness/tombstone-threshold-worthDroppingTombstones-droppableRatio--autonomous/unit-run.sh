#!/usr/bin/env bash
# Unit tier of tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous (B2 as amended, 2026-10-26).
# usage: unit-run.sh [run-name]   output: ~/s4-b10-td-logs/<run-name, default run1>/unit/
# Tree: $CASSANDRA_HOME (default ~/s4-b10-td-u, built with ant build-test). Copies the test into the tree, runs it with ant testsome,
# then analyze-unit.py (EXPECTED lines). No Byteman, no node. Stops on a failed check.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b10-td-u}; RUN=${1:-run1}
L=$HOME/s4-b10-td-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum TombstoneThresholdProbeTest.java analyze-unit.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/TombstoneThresholdProbeTest.java" test/unit/org/apache/cassandra/db/compaction/
rm -f "$L/test.out"; rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.TombstoneThresholdProbeTest \
  -Dtest.jvm.args="-Dstage4.out=$L/test.out" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.db.compaction.TombstoneThresholdProbeTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
echo "EXPECTED: the test ran to its end line — $(grep -q '^STAGE4 end' "$L/test.out" 2>/dev/null && echo yes || echo NO)" | tee -a "$S"
grep -q '^STAGE4 end' "$L/test.out" 2>/dev/null || { say "FAIL: test did not finish; see $L/ant.log"; exit 1; }
python3 "$H/analyze-unit.py" "$L/test.out" | tee "$L/analysis.txt" | tee -a "$S"
