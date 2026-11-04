#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.
# usage: unit-run.sh <run-label>      (run1: r1, r2, r3; the audit's compile check: unit-run.sh compile)
# Copies DenylistTotalTest.java into the run clone, runs `ant testsome` once, copies the JUnit XML and the test log, and extracts
# the "DLT " lines and the denylist ERROR lines (PartitionDenylist.java:425, :452, :486, :508) from the test log.
# Adapted from the sister case's unit-run.sh (not modified there).
# Output: $W/logs/denylist_max_keys_total-setDenylistMaxKeysTotal/unit-<label>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run26
LAB=${1:?label}
CLS=org.apache.cassandra.service.DenylistTotalTest
L=$W/logs/denylist_max_keys_total-setDenylistMaxKeysTotal/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/DenylistTotalTest.java" "$C/test/unit/org/apache/cassandra/service/" && echo "+ cp DenylistTotalTest.java -> clone" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/DenylistTotalTest.java" | cut -c1-12)"
if [ "$LAB" = compile ]; then
  echo "+ ant -Dlocal.repository=$W/m2 build-test > $L/ant.log" >> "$CL"
  ant -Dlocal.repository=$W/m2 build-test > "$L/ant.log" 2>&1 < /dev/null; say "compile exit=$? $(grep -m1 -o 'BUILD [A-Z]*' "$L/ant.log")"; exit 0
fi
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
grep -ho 'DLT .*' "$L"/TEST-*.log 2>/dev/null > "$L/stdout.txt"
grep -h 'Hit limit on allowable denylisted keys in total\|has exceeded the [a-z-]* allowance\|Error reading partition_denylist\|Error reading full partition denylist' "$L"/TEST-*.log 2>/dev/null > "$L/error-lines.txt"
say "DLT lines:"; cat "$L/stdout.txt" >> "$S"
say "Hit-limit lines: $(grep -c 'Hit limit' "$L/error-lines.txt") processed: $(grep -o 'Processed [0-9]* total entries. Not adding all entries to denylist for [a-z_]*/t[0-9]' "$L/error-lines.txt" | sed -E 's/Processed ([0-9]*) .* for (.*)/\1:\2/' | tr '\n' ' ')"
say "exceeded lines: $(grep -c 'has exceeded the' "$L/error-lines.txt") $(grep -o '[a-z_]*/t[0-9] has exceeded the [a-z-]* allowance of ([0-9]*)' "$L/error-lines.txt" | sed -E 's/ has exceeded the ([a-z-]*) allowance of \(([0-9]*)\)/:\1:\2/' | tr '\n' ' ')"
say "read-error lines: $(grep -c 'Error reading' "$L/error-lines.txt")"
say "Loaded lines: $(grep -h -c 'Loaded partition denylist cache' "$L"/TEST-*.log 2>/dev/null)"
say "other ERROR lines: $(grep -h '^ERROR' "$L"/TEST-*.log 2>/dev/null | grep -vc 'Hit limit on allowable\|has exceeded the [a-z-]* allowance')"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
