#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.
# usage: unit-run.sh <label>        labels: compile (instrument check), shake (DLP_SHAKE=1, not judged), r1 (run 1)
# Copies DenylistTotalCapProbeTest.java into the run clone, runs `ant testsome` once, copies the JUnit XML and the test log,
# extracts the "DLP " lines and the denylist log lines, then removes the copied source (clone's git status stays clean).
# Output: $W/logs/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed/unit-<label>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run41
LAB=${1:?label}
CLS=org.apache.cassandra.schema.DenylistTotalCapProbeTest
DST=$C/test/unit/org/apache/cassandra/schema/DenylistTotalCapProbeTest.java
L=$W/logs/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/DenylistTotalCapProbeTest.java" "$DST" && echo "+ cp DenylistTotalCapProbeTest.java -> $DST" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/DenylistTotalCapProbeTest.java" | cut -c1-12)"
if [ "$LAB" = compile ]; then
  echo "+ ant -Dlocal.repository=$W/m2 build-test > $L/ant.log" >> "$CL"
  ant -Dlocal.repository=$W/m2 build-test > "$L/ant.log" 2>&1 < /dev/null; say "compile exit=$? $(grep -m1 -o 'BUILD [A-Z]*' "$L/ant.log")"
  rm -f "$DST"; say "git status: $(git status --porcelain | wc -l | tr -d ' ') changed paths"; exit 0
fi
[ "$LAB" = shake ] && export DLP_SHAKE=1 || unset DLP_SHAKE
say "DLP_SHAKE=${DLP_SHAKE:-unset}"
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
rm -f "$DST"
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
grep -ho 'DLP .*' "$L"/TEST-*.log 2>/dev/null > "$L/stdout.txt"
grep -h 'DLP MARK\|Hit limit on allowable denylisted keys in total\|has exceeded the [a-z-]* allowance\|Error reading partition_denylist\|Error reading full partition denylist\|Loaded partition denylist cache' "$L"/TEST-*.log 2>/dev/null > "$L/denylist-lines.txt"
say "DLP lines:"; cat "$L/stdout.txt" >> "$S"
say "per segment (MARK -> hit / exceeded / read-errors / loaded):"
awk '/DLP MARK/{if(seg!="")print seg" hit="h" exceeded="x" readerr="e" loaded="l; sub(/.*DLP MARK /,""); seg=$0; h=x=e=l=0; next}
     /Hit limit on allowable/{h++} /has exceeded the/{x++} /Error reading/{e++} /Loaded partition denylist cache/{l++}
     END{print seg" hit="h" exceeded="x" readerr="e" loaded="l}' "$L/denylist-lines.txt" >> "$S"
say "git status: $(git status --porcelain | wc -l | tr -d ' ') changed paths"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
