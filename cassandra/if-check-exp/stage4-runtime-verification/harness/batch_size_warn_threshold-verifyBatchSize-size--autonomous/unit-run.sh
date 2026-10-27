#!/usr/bin/env bash
# Unit tier of batch_size_warn_threshold-verifyBatchSize-size--autonomous (B2 as amended A1-A4, 2026-10-26).
# usage: unit-run.sh [run-name]     output: ~/s4-b9-bs-logs/<run-name, default run1>/unit/
# Tree: $CASSANDRA_HOME (default ~/s4-b9-bs-u, built with ant build-test). Copies BatchWarnProbeTest, WarnBatches and
# stage4.Alloc into the tree's test sources, builds the helper jar for the boot class path, checks the Byteman script with
# TestScript, runs the test with the agent (agent port 19110, slot 1), then analyze.py. Stops on a failed check.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b9-bs-u}; RUN=${1:-run1}
L=$HOME/s4-b9-bs-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
BM=$C/build/lib/jars/byteman-4.0.20.jar
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum Alloc.java warn-size.btm WarnBatches.java BatchWarnProbeTest.java analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/BatchWarnProbeTest.java" "$H/WarnBatches.java" test/unit/org/apache/cassandra/transport/
mkdir -p test/unit/stage4 && cp "$H/Alloc.java" test/unit/stage4/
rm -rf "$L/alloc-classes" && mkdir -p "$L/alloc-classes" && javac -d "$L/alloc-classes" "$H/Alloc.java" && jar cf "$L/stage4-alloc.jar" -C "$L/alloc-classes" . || { say "FAIL: helper jar"; exit 1; }
java -cp "$BM:build/lib/jars/*:build/classes/main:lib/*:$L/stage4-alloc.jar" org.jboss.byteman.check.TestScript "$H/warn-size.btm" > "$L/testscript.log" 2>&1
NR=$(grep -c '^Type checked rule' "$L/testscript.log")
say "TestScript: $NR rules type checked; $(grep '^TestScript:' "$L/testscript.log")"
echo "EXPECTED: warn-size.btm type checks all 10 rules — $([ "$NR" = 10 ] && echo yes || echo NO)" | tee -a "$S"
[ "$NR" = 10 ] || { say "FAIL: Byteman script"; exit 1; }
rm -f "$L/test.out" "$L/warn-size.trace"
rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.transport.BatchWarnProbeTest \
  -Dtest.jvm.args="-javaagent:$BM=script:$H/warn-size.btm,port:19110 -Xbootclasspath/a:$L/stage4-alloc.jar -Dorg.jboss.byteman.verbose=false -Dstage4.out=$L/test.out -Dstage4.byteman.out=$L/warn-size.trace -Dstage4.count=${STAGE4_COUNT:-20}" \
  > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.transport.BatchWarnProbeTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException\|ParseException' "$L/ant.log" | head -5 | tee -a "$S"
grep '^STAGE4 check\|^STAGE4 info' "$L/test.out" | tee -a "$S"
echo "EXPECTED: instrument known-answer check ok — $(grep -q 'STAGE4 check alloc-known-answer.* ok' "$L/test.out" && echo yes || echo NO)" | tee -a "$S"
say "req lines: $(grep -c '^req ' "$L/test.out")"
python3 "$H/analyze.py" unit "$L/test.out" "$L/warn-size.trace" | tee "$L/analysis.txt" | tee -a "$S"
