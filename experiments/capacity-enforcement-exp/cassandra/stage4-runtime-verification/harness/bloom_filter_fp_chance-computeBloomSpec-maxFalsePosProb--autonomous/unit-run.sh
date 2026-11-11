#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-27, U1-U4) of bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.
# Adapted (sed of names, output-line pattern) from harness/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/unit-run.sh (that file is not modified).
# usage: unit-run.sh <label>      labels: compile (instrument check), shake (BFM_SHAKE=1, not judged), r1 (run 1)
# Copies BloomFpChanceMemoryTest.java into the run clone, runs `ant testsome` once, copies the JUnit XML and the test log,
# extracts the BFMSTART/BFSPEC/BFP/END lines, then removes the copied source (the clone's git status stays clean).
# Output: $W/logs/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/unit-<label>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run58
LAB=${1:?label}
CLS=org.apache.cassandra.utils.BloomFpChanceMemoryTest
DST=$C/test/unit/org/apache/cassandra/utils/BloomFpChanceMemoryTest.java
L=$W/logs/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/BloomFpChanceMemoryTest.java" "$DST" && echo "+ cp BloomFpChanceMemoryTest.java -> $DST" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test sha256 $(shasum -a 256 "$H/BloomFpChanceMemoryTest.java" | cut -c1-16)"
if [ "$LAB" = compile ]; then
  echo "+ ant -Dlocal.repository=$W/m2 build-test > $L/ant.log" >> "$CL"
  ant -Dlocal.repository=$W/m2 build-test > "$L/ant.log" 2>&1 < /dev/null; say "compile exit=$? $(grep -m1 -o 'BUILD [A-Z]*' "$L/ant.log")"
  rm -f "$DST"; say "git status: $(git status --porcelain | wc -l | tr -d ' ') changed paths"; exit 0
fi
[ "$LAB" = shake ] && export BFM_SHAKE=1 || unset BFM_SHAKE
say "BFM_SHAKE=${BFM_SHAKE:-unset}"
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
rm -f "$DST"
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
grep -hoE '(BFMSTART|BFSPEC|BFP|END) .*' "$L"/TEST-*.log 2>/dev/null > "$L/stdout.txt"
say "test lines:"; cat "$L/stdout.txt" >> "$S"
say "git status: $(git status --porcelain | wc -l | tr -d ' ') changed paths"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
