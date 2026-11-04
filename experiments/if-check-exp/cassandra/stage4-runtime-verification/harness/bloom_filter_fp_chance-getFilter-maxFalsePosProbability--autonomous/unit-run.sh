#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-27, U1-U5) of bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.
# Adapted from harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/unit-run.sh (that file is not modified):
# class name, env flag, Byteman agent via -Dtest.jvm.args, output-line pattern.
# usage: unit-run.sh <label>      labels: compile (instrument check), shake (BFG_SHAKE=1, not judged), r1 (run 1)
# Copies BloomFpChanceSizeTest.java into the run clone, runs `ant testsome` once with the bf-unit.btm agent, copies the JUnit XML
# and the test log, extracts the BFSTART/BFMARK/BFP/END/BMBF lines, then removes the copied source (clone git status stays clean).
# Output: $W/logs/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/unit-<label>/
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run59
LAB=${1:?label}
CLS=org.apache.cassandra.utils.BloomFpChanceSizeTest
DST=$C/test/unit/org/apache/cassandra/utils/BloomFpChanceSizeTest.java
L=$W/logs/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/unit-$LAB
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cp "$H/BloomFpChanceSizeTest.java" "$DST" && echo "+ cp BloomFpChanceSizeTest.java -> $DST" >> "$CL"
cd "$C"
say "unit-run $LAB $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test sha256 $(shasum -a 256 "$H/BloomFpChanceSizeTest.java" | cut -c1-16) btm sha256 $(shasum -a 256 "$H/bf-unit.btm" | cut -c1-16)"
if [ "$LAB" = compile ]; then
  echo "+ ant -Dlocal.repository=$W/m2 build-test > $L/ant.log" >> "$CL"
  ant -Dlocal.repository=$W/m2 build-test > "$L/ant.log" 2>&1 < /dev/null; say "compile exit=$? $(grep -m1 -o 'BUILD [A-Z]*' "$L/ant.log")"
  rm -f "$DST"; say "git status: $(git status --porcelain | wc -l | tr -d ' ') changed paths"; exit 0
fi
[ "$LAB" = shake ] && export BFG_SHAKE=1 || unset BFG_SHAKE
say "BFG_SHAKE=${BFG_SHAKE:-unset}"
AGENT="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/bf-unit.btm"
rm -rf build/test/output/TEST-$CLS*.xml build/test/logs
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=$AGENT > $L/ant.log" >> "$CL"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$CLS "-Dtest.jvm.args=$AGENT" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
find build/test/output -name "TEST-$CLS*.xml" -exec cp {} "$L/" \;
find build/test/logs -name "TEST-$CLS*.log" -exec cp {} "$L/" \; 2>/dev/null
rm -f "$DST"
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(grep -m1 -o 'Total time: .*' "$L/ant.log")"
say "files: $(cd "$L" && ls | tr '\n' ' ')"
grep -hoE '(BFSTART|BFMARK|BFP|END|BMBF) .*' "$L"/TEST-*.log 2>/dev/null > "$L/stdout.txt"
grep -hoE '(BFSTART|BFMARK|BFP|END|BMBF) .*' "$L"/TEST-*.xml 2>/dev/null > "$L/stdout-xml.txt"
say "lines in test log: $(wc -l < "$L/stdout.txt" | tr -d ' ') (BFP $(grep -c '^BFP ' "$L/stdout.txt"), BMBF $(grep -c '^BMBF ' "$L/stdout.txt")); in junit xml: $(wc -l < "$L/stdout-xml.txt" | tr -d ' ')"
say "BFSTART/BFP/END lines:"; grep -E '^(BFSTART|BFP|END) ' "$L/stdout.txt" >> "$S"
say "git status: $(git status --porcelain | wc -l | tr -d ' ') changed paths"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
