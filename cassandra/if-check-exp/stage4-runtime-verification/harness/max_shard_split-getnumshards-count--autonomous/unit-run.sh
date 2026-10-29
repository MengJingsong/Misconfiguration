#!/usr/bin/env bash
# usage: unit-run.sh <copy dir> <out dir>   (case B2, 2026-10-28). Copies ShardCapProbeTest into the run copy's test tree (the copy, never the repository), runs it with ant testsome
# (-Xmx1g; build.xml already selects G1 and a second collector flag aborts the JVM with "Multiple garbage collectors selected", so of B2a cannot be added: runbook defect 1), then the upstream ControllerTest#testGetNumShards as a known-answer check of the instrument; unit.out holds the STAGE4 lines.
set -uo pipefail
C=${1:?copy dir}; OUT=${2:?out dir}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$C/test/unit/org/apache/cassandra/db/compaction/unified"
cp "$H/ShardCapProbeTest.java" "$C/test/unit/org/apache/cassandra/db/compaction/unified/"
cd "$C"
for rep in 1 2; do   # two independent JVMs
  ant testsome -Dtest.name=org.apache.cassandra.db.compaction.unified.ShardCapProbeTest -Dtest.jvm.args="-Xmx1g" </dev/null > "$OUT/ant-probe-$rep.log" 2>&1
  echo "probe rep $rep: $(grep -E 'BUILD|Tests run' "$OUT/ant-probe-$rep.log" | tr '\n' ' ')"
  grep -o 'STAGE4 .*' "$OUT/ant-probe-$rep.log" > "$OUT/unit-$rep.out"
done
ant testsome -Dtest.name=org.apache.cassandra.db.compaction.unified.ControllerTest -Dtest.methods=testGetNumShards </dev/null > "$OUT/ant-controllertest.log" 2>&1
echo "ControllerTest#testGetNumShards: $(grep -E 'BUILD|Tests run' "$OUT/ant-controllertest.log" | tr '\n' ' ')"
ps -eo cmd | grep -E '[A]ntRunner|[J]UnitTask' || echo "no ant/junit processes left"
