#!/usr/bin/env bash
# Unit tier (B2 as amended U1-U4, 2026-10-27) of repair_session_space-initHelper-max--autonomous.
# usage: unit-run.sh instrument|shake|run
#   instrument  copy the test, compile it (ant build-test), run upstream ValidatorTest (known answer: testSizeLimiting, 2^12 leaves at 1 MiB)
#   shake       RepairSessionSpaceProbeTest with 2^12 keys, S=1 and control 2 (harness shakedown, not judged)
#   run         RepairSessionSpaceProbeTest as amended (2^18 keys, S=1,2,4,8,16, control 64)
# Output: $W/logs/repair_session_space-initHelper-max--autonomous/unit-<mode>/ (commands.log, summary.txt, stage4.out, ant log, JUnit XML)
# Adapted from harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/unit-run.sh.
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run60
what=${1:?instrument|shake|run}
L=$W/logs/repair_session_space-initHelper-max--autonomous/unit-$what
rm -rf "$L"; mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cmd() { echo "+ $*" >> "$CL"; "$@" >> "$CL" 2>&1; local rc=$?; echo "  exit=$rc" >> "$CL"; return $rc; }
cmd cp "$H/RepairSessionSpaceProbeTest.java" "$C/test/unit/org/apache/cassandra/repair/"
cd "$C"
say "unit-run $what $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test md5 $(md5 -q "$H/RepairSessionSpaceProbeTest.java" | cut -c1-12)"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  local log="$L/$(basename ${cls//./_}).ant.log"
  echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$cls $*  > $log" >> "$CL"
  ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$cls "$@" > "$log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  find build/test/logs -name "TEST-$cls.log" -exec cp {} "$L/" \; 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$log") $(grep -m1 -o 'Total time: .*' "$log")"
}
P=org.apache.cassandra.repair.RepairSessionSpaceProbeTest
case $what in
  instrument)
    cmd ant -Dlocal.repository=$W/m2 build-test && say "build-test with RepairSessionSpaceProbeTest: BUILD SUCCESSFUL" || say "build-test FAILED"
    run org.apache.cassandra.repair.ValidatorTest
    say "ValidatorTest testSizeLimiting: $(grep -o '<testcase [^>]*name="testSizeLimiting[^"]*"[^>]*>' "$L"/TEST-org.apache.cassandra.repair.ValidatorTest*.xml | head -1) failures-in-it: $(grep -A2 "name=\"testSizeLimiting" "$L"/TEST-org.apache.cassandra.repair.ValidatorTest*.xml | grep -c '<failure\|<error')"
    ;;
  shake)
    run $P -Dtest.jvm.args="-Dstage4.out=$L/stage4.out -Dstage4.keys=4096 -Dstage4.svalues=1 -Dstage4.control=2" -Dtest.timeout=1800000 ;;
  run)
    run $P -Dtest.jvm.args="-Dstage4.out=$L/stage4.out" -Dtest.timeout=1800000 ;;
esac
if [ "$what" != instrument ]; then
  say "STAGE4 readings: $(grep -c '^STAGE4 reading' "$L/stage4.out" 2>/dev/null)"
  cat "$L/stage4.out" >> "$S" 2>/dev/null
fi
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
