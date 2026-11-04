#!/usr/bin/env bash
# Unit tier of max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous.
# usage (on the measured node): unit-run.sh <tree> <logdir> [plain|instrument]
#   plain       HintsFileSizeLimitTest only (a shakedown without Byteman)
#   instrument  the same with mh.btm attached: roll / sessclose / decide lines go to <logdir>/mh.trace (the run of record)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
C=${1:?tree}; L=${2:?logdir}; what=${3:-instrument}
ulimit -n 100000
mkdir -p "$L"; S=$L/summary.txt; : > "$S"; rm -f "$L/harness.out" "$L/mh.trace"
cp "$H/HintsFileSizeLimitTest.java" "$C/test/unit/org/apache/cassandra/hints/"
cd "$C"
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) tree $(git describe --tags) harness md5 $(md5sum "$H/HintsFileSizeLimitTest.java" | cut -c1-12) rules md5 $(md5sum "$H/mh.btm" | cut -c1-12)"
rm -rf build/test/cassandra/hints
JV="-Dstage4.out=$L/harness.out"
if [ "$what" = instrument ]; then
  JV="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/mh.btm -Dorg.jboss.byteman.verbose=false -Dstage4.trace=$L/mh.trace $JV"
fi
cls=org.apache.cassandra.hints.HintsFileSizeLimitTest
ant testsome -Dtest.name=$cls -Dtest.jvm.args="$JV" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out" 2>/dev/null) MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out" 2>/dev/null)"
grep 'MISMATCH' "$L/harness.out" 2>/dev/null | tee -a "$S"
grep '^STAGE4 summary' "$L/harness.out" 2>/dev/null | tee -a "$S"
if [ "$what" = instrument ]; then
  for pat in '^roll ' '^sessclose ' '^decide ' '^decide .*result=false'; do say "trace '$pat': $(grep -c "$pat" "$L/mh.trace" 2>/dev/null)"; done
  grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException' "$L/ant.log" | head -5 | tee -a "$S"
fi
