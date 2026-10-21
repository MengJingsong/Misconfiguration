#!/usr/bin/env bash
# Unit tier (B2) of maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.
# usage: unit-run.sh <orig|fixed> [run-name]     output: ~/stage4-logs/mhp/<run-name, default run1>/unit-<orig|fixed>/
# orig = ~/cassandra-mhp (cassandra-5.0.9 as tagged), fixed = ~/cassandra-mhp-patched (hintsInProgress-LoadingCache.diff).
# Checks the build (javap: the field type of StorageProxy.hintsInProgress in build/classes/main), copies
# HintOverloadCheckTest.java into test/unit/org/apache/cassandra/service/, runs ant testsome (B2e step 2), copies the
# JUnit XML and extracts the INFO / RESULT / DRAINED lines into summary.txt (B2e step 3). The test stays in the clone.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); B=${1:?orig|fixed}; RUN=${2:-run1}
case $B in orig) C=$HOME/cassandra-mhp ;; fixed) C=$HOME/cassandra-mhp-patched ;; *) echo "orig|fixed" >&2; exit 2 ;; esac
L=$HOME/stage4-logs/mhp/$RUN/unit-$B; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $B $(date -Is) host $(hostname -s) clone $C $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum HintOverloadCheckTest.java unit-run.sh hintsInProgress-LoadingCache.diff | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "clone diff vs tag (src/java): $(git diff --stat -- src/java | tail -1)"
say "field: $(javap -p -cp build/classes/main org.apache.cassandra.service.StorageProxy | grep ' hintsInProgress;' | sed 's/^ *//')"
cp "$H/HintOverloadCheckTest.java" test/unit/org/apache/cassandra/service/HintOverloadCheckTest.java
rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.service.HintOverloadCheckTest > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.service.HintOverloadCheckTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
# The test JVM routes System.out through a logger (SubstituteLogger) that logs every write of printf as its own line
# (harness defect H1, unit run 1): join the fragments of the test's own lines, from INFO maxHeapMiB= on, back into lines.
sed -n '/SubstituteLogger.java:[0-9]* - INFO maxHeapMiB=/,$p' "$L/ant.log" | grep 'SubstituteLogger.java:[0-9]* - ' \
  | sed 's/.*SubstituteLogger.java:[0-9]* - //' | tr '\n' ' ' | sed 's/ \(RESULT L=\|DRAINED L=\)/\n\1/g; s/  */ /g; s/= /=/g' \
  | sed 's/ *$//' > "$L/lines.txt"; echo >> "$L/lines.txt"
tee -a "$S" < "$L/lines.txt"
say "done $(date -Is)"
