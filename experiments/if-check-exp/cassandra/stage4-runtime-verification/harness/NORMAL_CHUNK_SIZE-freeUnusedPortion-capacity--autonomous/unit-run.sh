#!/bin/bash
# Stage-4 unit tier (case file B2e, amended 2026-10-22) for NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.
# usage: bash unit-run.sh <outdir>   (run from a frozen copy of the harness; CASSANDRA_HOME defaults to ~/cassandra-ncs)
# Logs every command and its output to <outdir>/unit-run.log; extracts INFO/ROW/PUT/SHIFT/CTL lines to <outdir>/unit-lines.txt.
set -u
C=${CASSANDRA_HOME:-$HOME/cassandra-ncs}
H=$(cd "$(dirname "$0")" && pwd)
OUT=${1:?outdir}
mkdir -p "$OUT"
LOG=$OUT/unit-run.log
exec > >(tee -a "$LOG") 2>&1
run() { echo "+ $*  [$(date +%F' '%T)]"; "$@"; local rc=$?; echo "  rc=$rc"; return $rc; }
T=test/unit/org/apache/cassandra/utils/memory/FreeUnusedPortionProbeTest.java
cd "$C" || exit 1
run git -C "$C" describe --tags
run git -C "$C" rev-parse HEAD
run java -version
run cp "$H/FreeUnusedPortionProbeTest.java" "$C/$T"
run sha256sum "$H/FreeUnusedPortionProbeTest.java" "$C/$T"
# step 2: the probe test
run ant testsome -Dtest.name=org.apache.cassandra.utils.memory.FreeUnusedPortionProbeTest </dev/null
X=build/test/output/TEST-org.apache.cassandra.utils.memory.FreeUnusedPortionProbeTest.xml
run cp "$X" "$OUT/probe-junit.xml"
# step 3: extract. Runbook-defect fix D2 (2026-10-22): the XML holds the test's stdout only when a test fails, so the lines
# are taken from the ant console output in this log (the [junit-timeout] lines of the probe test's run).
sed -n '/Testsuite: org.apache.cassandra.utils.memory.FreeUnusedPortionProbeTest/,/^BUILD /p' "$LOG" | grep -oE '(INFO|ROW|PUT|SHIFT|CTL),[^<&]*' > "$OUT/unit-lines.txt"; echo "lines: $(wc -l < "$OUT/unit-lines.txt")"
grep -oE '<testsuite [^>]*>' "$X" | head -1
# step 4: the shipped reference test
run ant testsome -Dtest.name=org.apache.cassandra.utils.memory.BufferPoolTest -Dtest.methods=testPuttingUnusedPortion </dev/null
X2=build/test/output/TEST-org.apache.cassandra.utils.memory.BufferPoolTest-testPuttingUnusedPortion.xml
run cp "$X2" "$OUT/shipped-junit.xml"
grep -oE '<testsuite [^>]*>' "$X2" | head -1
# leave the clone as it was
run rm -f "$C/$T"
run git -C "$C" status --short
echo "unit-run done $(date +%F' '%T)"
