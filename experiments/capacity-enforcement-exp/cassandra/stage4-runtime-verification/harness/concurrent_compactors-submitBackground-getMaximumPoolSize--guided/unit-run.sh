#!/usr/bin/env bash
# Unit tier of concurrent_compactors-submitBackground-getMaximumPoolSize (case 9c): copies the probe test into the local clone and
# runs it with ant testsome. usage: unit-run.sh [suffix]   output: ~/stage4-logs/cc/unit[-suffix]/{run.out,ant.log,summary.txt}
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run4}; L=$HOME/stage4-logs/cc/unit${1:+-$1}
mkdir -p "$L"; rm -f "$L/run.out" "$L/summary.txt"
cp "$H/ConcurrentCompactorsProbeTest.java" "$C/test/unit/org/apache/cassandra/db/compaction/"
cd "$C"
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.ConcurrentCompactorsProbeTest -Dtest.jvm.args="-Dstage4.out=$L/run.out" > "$L/ant.log" 2>&1
rc=$?
echo "ant rc=$rc; $(grep -m1 'Tests run' "$L/ant.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant.log") BUILD FAILED" | tee -a "$L/summary.txt"
cat "$L/run.out" 2>/dev/null | tee -a "$L/summary.txt"
