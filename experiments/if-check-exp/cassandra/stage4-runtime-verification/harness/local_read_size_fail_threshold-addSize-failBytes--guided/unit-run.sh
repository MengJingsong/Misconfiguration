#!/usr/bin/env bash
# Unit tier of local_read_size_fail_threshold-addSize-failBytes (case 9c/9e): copies the harness test into the local clone and runs it in one JVM.
# usage (on the measured node): unit-run.sh        output: ~/stage4-logs/lrs/unit/{run.out,ant.log}
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=$HOME/stage4-logs/lrs/unit
mkdir -p "$L"; cp "$H/LocalReadSizeGuardTest.java" "$C/test/unit/org/apache/cassandra/db/"
cd "$C"; rm -f "$L/run.out"
ant testsome -Dtest.name=org.apache.cassandra.db.LocalReadSizeGuardTest -Dtest.jvm.args="-Dstage4.out=$L/run.out" > "$L/ant.log" 2>&1 || true
grep "Tests run" "$L/ant.log" | head -2
echo "MISMATCH lines: $(grep -c MISMATCH "$L/run.out" || true)"; tail -1 "$L/run.out"
