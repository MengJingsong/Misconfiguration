#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.
# usage: unit-run.sh <run-label>      e.g. unit-run.sh r1   (run three times: r1, r2, r3)
# Copies BatchlogPageBudgetTest.java into the run clone, runs `ant testsome` once (one JVM, four cases), and copies the JUnit XML
# and the test log. Output: $W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/unit-<label>/ (commands.log, summary.txt,
# ant.log, TEST-*.xml, TEST-*.log, stdout.txt = the test's "BLP " lines read from the test log).
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run28
LAB=${1:?label}
CLS=org.apache.cassandra.batchlog.BatchlogPageBudgetTest
L=$W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/BatchlogPageBudgetTest.java" "$C/test/unit/org/apache/cassandra/batchlog/" && echo "+ cp BatchlogPageBudgetTest.java -> clone" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/BatchlogPageBudgetTest.java" | cut -c1-12)"
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
cat "$L"/TEST-*.log 2>/dev/null | grep -o 'BLP .*' > "$L/stdout.txt"
say "stdout lines:"; sed 's/^/  /' "$L/stdout.txt" | cut -c1-400 >> "$S"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
