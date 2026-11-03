#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-24) of repair_session_space-applySimpleConfig-repair_session_space--autonomous.
# usage: unit-run.sh [instrument|run]
#   instrument  copy the test, compile it (ant build-test), run upstream ValidatorTest (known answer: testSizeLimiting 2^12 at 1 MiB)
#   run         ValidatorSpaceCapTest; STAGE4 lines in stage4.out
# Output: $W/logs/repair_session_space-applySimpleConfig/unit[-instrument]/ (commands.log, summary.txt, ant logs, JUnit XML)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run4
what=${1:-run}
L=$W/logs/repair_session_space-applySimpleConfig/unit; [ "$what" = instrument ] && L=$L-instrument
mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cmd() { echo "+ $*" >> "$CL"; "$@" >> "$CL" 2>&1; local rc=$?; echo "  exit=$rc" >> "$CL"; return $rc; }
cmd cp "$H/ValidatorSpaceCapTest.java" "$C/test/unit/org/apache/cassandra/repair/"
cd "$C"
say "unit-run $what $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) harness md5 $(md5 -q "$H/ValidatorSpaceCapTest.java" | cut -c1-12)"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  local log="$L/$(basename ${cls//./_}).ant.log"
  echo "+ ant testsome -Dtest.name=$cls $*  > $log" >> "$CL"
  ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$cls "$@" > "$log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$log") $(grep -m1 -o 'Total time: .*' "$log")"
}
if [ "$what" = instrument ]; then
  cmd ant -Dlocal.repository=$W/m2 build-test && say "build-test with ValidatorSpaceCapTest: BUILD SUCCESSFUL" || say "build-test FAILED"
  run org.apache.cassandra.repair.ValidatorTest
fi
if [ "$what" = run ]; then
  rm -f "$L/stage4.out"
  run org.apache.cassandra.repair.ValidatorSpaceCapTest -Dtest.jvm.args="-Dstage4.out=$L/stage4.out" -Dtest.timeout=1800000
  say "STAGE4 readings: $(grep -c '^STAGE4 reading' "$L/stage4.out" 2>/dev/null)"
  cat "$L/stage4.out" >> "$S" 2>/dev/null
fi
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
