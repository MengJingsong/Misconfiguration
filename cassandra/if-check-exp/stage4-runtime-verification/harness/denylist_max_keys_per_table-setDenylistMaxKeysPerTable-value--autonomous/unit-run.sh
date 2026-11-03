#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.
# usage: unit-run.sh <run-label>      (run1: r1, r2, r3; the audit's compile check: unit-run.sh compile)
# Copies DenylistPerTableTest.java into the run clone, runs `ant testsome` once, copies the JUnit XML and the test log, and extracts
# the "DLPT " lines and the per-table ERROR lines (PartitionDenylist.java:425) from the test log.
# Output: $W/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/unit-<label>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run25
LAB=${1:?label}
CLS=org.apache.cassandra.service.DenylistPerTableTest
L=$W/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/DenylistPerTableTest.java" "$C/test/unit/org/apache/cassandra/service/" && echo "+ cp DenylistPerTableTest.java -> clone" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/DenylistPerTableTest.java" | cut -c1-12)"
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
grep -ho 'DLPT .*' "$L"/TEST-*.log 2>/dev/null > "$L/stdout.txt"
grep -h 'has exceeded the [a-z-]* allowance' "$L"/TEST-*.log 2>/dev/null > "$L/error-lines.txt"
say "DLPT lines:"; cat "$L/stdout.txt" >> "$S"
say "ERROR exceeded lines: $(grep -c . "$L/error-lines.txt") allowances: $(grep -o 'exceeded the [a-z-]* allowance of ([0-9]*)' "$L/error-lines.txt" | sed -E 's/exceeded the ([a-z-]*) allowance of \(([0-9]*)\)/\1:\2/' | tr '\n' ' ')"
say "other ERROR lines: $(grep -h '^ERROR' "$L"/TEST-*.log 2>/dev/null | grep -vc 'has exceeded the [a-z-]* allowance')"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
