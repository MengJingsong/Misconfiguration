#!/usr/bin/env bash
# Unit tier of DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace (case 9c/9e, amended 2026-10-15):
# copies WriteDirectoryGuardTest into the local clone and runs upstream CompactionAwareWriterTest once and the harness test once
# per partitioner, one ant call each.
# usage (on the measured node): unit-run.sh [suffix]      output: ~/stage4-logs/dds/unit[-suffix]/{run.out,ant-<name>.log,summary.txt}
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run3}; L=$HOME/stage4-logs/dds/unit${1:+-$1}
mkdir -p "$L"; rm -f "$L/run.out" "$L/summary.txt"
cp "$H/WriteDirectoryGuardTest.java" "$C/test/unit/org/apache/cassandra/db/compaction/writers/"
cd "$C"
run() {  # name, test class, extra jvm args
  ant testsome -Dtest.name="$2" -Dtest.jvm.args="-Dstage4.out=$L/run.out -Dorg.jboss.byteman.contrib.bmunit.agent.port=19091 $3" > "$L/ant-$1.log" 2>&1
  rc=$?
  echo "$1: ant rc=$rc; $(grep -m1 'Tests run' "$L/ant-$1.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant-$1.log") BUILD FAILED" | tee -a "$L/summary.txt"
}
run CompactionAwareWriterTest org.apache.cassandra.db.compaction.writers.CompactionAwareWriterTest ""
run guard-BOP org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest "-Dstage4.partitioner=ByteOrderedPartitioner"
run guard-M3 org.apache.cassandra.db.compaction.writers.WriteDirectoryGuardTest "-Dstage4.partitioner=Murmur3Partitioner"
echo "checks: $(grep -c ' check ' "$L/run.out" 2>/dev/null || echo 0); MISMATCH lines: $(grep -c MISMATCH "$L/run.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException' "$L"/ant-*.log | head -5 | tee -a "$L/summary.txt"
