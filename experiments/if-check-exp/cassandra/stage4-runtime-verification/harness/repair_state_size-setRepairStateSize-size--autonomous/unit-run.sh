#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of repair_state_size-setRepairStateSize-size--autonomous.
# usage: unit-run.sh <run-label>      e.g. unit-run.sh r1   (run three times: r1, r2, r3)
# Copies RepairStateSizeTest.java into the run clone, runs `ant testsome` once with MBean registration disabled, and copies the
# JUnit XML and the test log. Output: $W/logs/repair_state_size-setRepairStateSize/unit-<label>/ (commands.log, summary.txt,
# ant.log, TEST-*.xml, TEST-*.log, stdout.txt = the test's "RSS " lines, storing.txt = "Storing repair state" lines,
# setting.txt = "Setting repair_state_size" lines, all read from the test log).
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run27
LAB=${1:?label}
CLS=org.apache.cassandra.service.RepairStateSizeTest
L=$W/logs/repair_state_size-setRepairStateSize/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/RepairStateSizeTest.java" "$C/test/unit/org/apache/cassandra/service/" && echo "+ cp RepairStateSizeTest.java -> clone" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/RepairStateSizeTest.java" | cut -c1-12)"
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=-Dorg.apache.cassandra.disable_mbean_registration=true > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS "-Dtest.jvm.args=-Dorg.apache.cassandra.disable_mbean_registration=true" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
cat "$L"/TEST-*.log 2>/dev/null | grep -o 'RSS .*' > "$L/stdout.txt"
cat "$L"/TEST-*.log 2>/dev/null | grep 'Storing repair state for' > "$L/storing.txt"
cat "$L"/TEST-*.log 2>/dev/null | grep 'Setting repair_state_size to' > "$L/setting.txt"
say "stdout lines:"; sed 's/^/  /' "$L/stdout.txt" >> "$S"
say "storing lines: $(wc -l < "$L/storing.txt" | tr -d ' ') values: $(grep -o 'or for [0-9]* elements' "$L/storing.txt" | awk '{print $3}' | tr '\n' ' ')"
say "setting lines: $(wc -l < "$L/setting.txt" | tr -d ' ') values: $(grep -o 'repair_state_size to [0-9]*' "$L/setting.txt" | awk '{print $3}' | tr '\n' ' ')"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
