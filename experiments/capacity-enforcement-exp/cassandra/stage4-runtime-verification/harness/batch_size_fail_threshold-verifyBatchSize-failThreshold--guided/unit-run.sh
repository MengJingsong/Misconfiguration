#!/usr/bin/env bash
# Unit tier of batch_size_fail_threshold-verifyBatchSize-failThreshold--guided (case 9a Procedure 1, amended R8 2026-10-20).
# usage (on the measured node): unit-run.sh [run-name]      output: ~/stage4-logs/bsf/<run-name, default run1>/unit/
# Copies BatchSizeAllocTest, SendBatches and stage4.Alloc into the clone's test tree, builds the helper jar for the boot
# class path, checks the Byteman script with TestScript, runs the test with the agent, then analyze.py on its output.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; RUN=${1:-run1}
L=$HOME/stage4-logs/bsf/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
BM=$C/build/lib/jars/byteman-4.0.20.jar
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum Alloc.java batch-alloc.btm SendBatches.java BatchSizeAllocTest.java analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/BatchSizeAllocTest.java" "$H/SendBatches.java" test/unit/org/apache/cassandra/transport/
mkdir -p test/unit/stage4 && cp "$H/Alloc.java" test/unit/stage4/
rm -rf "$L/alloc-classes" && mkdir -p "$L/alloc-classes" && javac -d "$L/alloc-classes" "$H/Alloc.java" && jar cf "$L/stage4-alloc.jar" -C "$L/alloc-classes" . || { say "FAIL: helper jar"; exit 1; }
# parse and type-check the rules against the built classes
java -cp "$BM:build/lib/jars/*:build/classes/main:lib/*:$L/stage4-alloc.jar" org.jboss.byteman.check.TestScript "$H/batch-alloc.btm" > "$L/testscript.log" 2>&1
say "TestScript: $(grep -c '^Type checked rule' "$L/testscript.log") rules type checked; $(grep '^TestScript:' "$L/testscript.log")"
rm -f "$L/test.out" "$L/batch-alloc.trace"
rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.transport.BatchSizeAllocTest \
  -Dtest.jvm.args="-javaagent:$BM=script:$H/batch-alloc.btm -Xbootclasspath/a:$L/stage4-alloc.jar -Dorg.jboss.byteman.verbose=false -Dstage4.out=$L/test.out -Dstage4.byteman.out=$L/batch-alloc.trace" \
  > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.transport.BatchSizeAllocTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException\|ParseException' "$L/ant.log" | head -5 | tee -a "$S"
grep '^STAGE4 check\|^STAGE4 info' "$L/test.out" | tee -a "$S"
say "req lines: $(grep -c '^req ' "$L/test.out")"
python3 "$H/analyze.py" unit "$L/test.out" "$L/batch-alloc.trace" | tee "$L/analysis.txt" | tee -a "$S"
