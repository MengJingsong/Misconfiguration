#!/usr/bin/env bash
# Unit tier of native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided (case 9a
# Procedure step 1, amended 9f R2-R4, 2026-10-20).
# usage (on the measured node): unit-run.sh [run-name]      output: ~/stage4-logs/nqa/<run-name, default run1>/unit/
# Copies NqaQueueAgeTest and QueueAgeWriter into the clone's test tree (transport/) and NqaHold into test/unit/stage4/,
# type-checks nqa.btm with TestScript, then runs the test with the Byteman agent (nqa.btm). The release file and the
# trace are under the output folder.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; RUN=${1:-run1}
L=$HOME/stage4-logs/nqa/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
BM=$C/build/lib/jars/byteman-4.0.20.jar
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum NqaHold.java nqa.btm QueueAgeWriter.java NqaQueueAgeTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/NqaQueueAgeTest.java" "$H/QueueAgeWriter.java" test/unit/org/apache/cassandra/transport/
mkdir -p test/unit/stage4 && cp "$H/NqaHold.java" test/unit/stage4/
rm -rf "$L/hold-classes" && mkdir -p "$L/hold-classes" && javac -d "$L/hold-classes" "$H/NqaHold.java" || { say "FAIL: NqaHold compile"; exit 1; }
java -cp "$BM:build/lib/jars/*:build/classes/main:lib/*:$L/hold-classes" org.jboss.byteman.check.TestScript "$H/nqa.btm" > "$L/testscript.log" 2>&1
say "TestScript: $(grep -c '^Type checked rule' "$L/testscript.log") rules type checked; $(grep '^TestScript:' "$L/testscript.log")"
grep -q 'TestScript: no errors' "$L/testscript.log" || { say "FAIL: TestScript"; cat "$L/testscript.log" | tail -20 | tee -a "$S"; exit 1; }
rm -f "$L/test.out" "$L/nqa.trace"; touch "$L/release.flag"
rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.transport.NqaQueueAgeTest \
  -Dtest.jvm.args="-javaagent:$BM=script:$H/nqa.btm -Dorg.jboss.byteman.verbose=false -Dstage4.out=$L/test.out -Dstage4.trace=$L/nqa.trace -Dstage4.release.file=$L/release.flag" \
  > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.transport.NqaQueueAgeTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException\|ParseException' "$L/ant.log" | head -5 | tee -a "$S"
say "trace: hold in $(grep -c '^hold in ' "$L/nqa.trace" 2>/dev/null), hold out $(grep -c '^hold out ' "$L/nqa.trace" 2>/dev/null), chk $(grep -c '^chk ' "$L/nqa.trace" 2>/dev/null) (ret=false $(grep -c '^chk .* ret=false' "$L/nqa.trace" 2>/dev/null))"
grep '^STAGE4' "$L/test.out" | tee -a "$S" > /dev/null
say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c 'MISMATCH' "$L/test.out")"
grep 'MISMATCH' "$L/test.out" | sed 's/^/  /' | tee -a "$S"
grep '^STAGE4 arm\|^STAGE4 summary' "$L/test.out"
