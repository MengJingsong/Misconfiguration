#!/usr/bin/env bash
# Unit tier of max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction (case 9c/9e):
# copies the two harness tests into the local clone and runs the three upstream classes and the two harness classes, one ant call each.
# usage (on the measured node): unit-run.sh [suffix]      output: ~/stage4-logs/mscp/unit[-suffix]/{run.out,ant-<class>.log,summary.txt}
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=$HOME/stage4-logs/mscp/unit${1:+-$1}
mkdir -p "$L"; rm -f "$L/run.out" "$L/summary.txt"
cp "$H/CompactionBudgetTest.java" "$C/test/unit/org/apache/cassandra/db/"
cp "$H/CompactionLadderTest.java" "$C/test/unit/org/apache/cassandra/db/compaction/"
cd "$C"
for t in org.apache.cassandra.db.DirectoriesTest org.apache.cassandra.db.compaction.CompactionsBytemanTest \
         org.apache.cassandra.db.compaction.PartialCompactionsTest org.apache.cassandra.db.CompactionBudgetTest \
         org.apache.cassandra.db.compaction.CompactionLadderTest; do
  n=${t##*.}
  ant testsome -Dtest.name="$t" -Dtest.jvm.args="-Dstage4.out=$L/run.out" > "$L/ant-$n.log" 2>&1
  rc=$?
  echo "$n: ant rc=$rc; $(grep -m1 'Tests run' "$L/ant-$n.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant-$n.log") BUILD FAILED" | tee -a "$L/summary.txt"
done
echo "MISMATCH lines: $(grep -c MISMATCH "$L/run.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
tail -1 "$L/run.out" 2>/dev/null || true
