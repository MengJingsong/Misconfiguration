#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-24) of cdc_total_space-applySimpleConfig-cdc_total_space--autonomous.
# usage: unit-run.sh [instrument|run]
#   instrument  copy CDCAllowanceTest, compile (ant build-test), run upstream CommitLogSegmentManagerCDCTest (known answer:
#               all pass) and CDCAllowanceTest scenario=helper (known answer: 512 and 4096)
#   run         nine JVMs: block s=8,16,32; nonblock s=8,16,32; ctl-plain; ctl-1024; helper
# Output: $W/logs/cdc_total_space-applySimpleConfig/unit[-instrument]/ (commands.log, summary.txt, <jvm>.ant.log,
#         <jvm>.stage4.out, JUnit XML)
set -uo pipefail
source ~/Library/Caches/stage4/env.sh
H=$(cd "$(dirname "$0")" && pwd); C=$W/cassandra-run6
what=${1:-run}
L=$W/logs/cdc_total_space-applySimpleConfig/unit; [ "$what" = instrument ] && L=$L-instrument
[ -e "$L" ] && mv "$L" "$L.attempt-$(date +%s)"
mkdir -p "$L"; S=$L/summary.txt; CL=$L/commands.log; : > "$S"; : > "$CL"
say() { echo "$*" | tee -a "$S" >> "$CL"; }
cmd() { echo "+ $*" >> "$CL"; "$@" >> "$CL" 2>&1; local rc=$?; echo "  exit=$rc" >> "$CL"; return $rc; }
d=$(ps -eo command | grep '[C]assandraDaemon'); [ -n "$d" ] && { say "ABORT: a CassandraDaemon is running"; exit 1; }
cmd cp "$H/CDCAllowanceTest.java" "$C/test/unit/org/apache/cassandra/db/commitlog/"
cd "$C"
say "unit-run $what $(date '+%Y-%m-%dT%H:%M:%S%z') clone $(git describe --tags) $(git rev-parse --short HEAD) test sha256 $(shasum -a 256 "$H/CDCAllowanceTest.java" | cut -c1-16) java $(java -version 2>&1 | head -1)"
run() {   # run <label> <class> [jvm args]
  local lab=$1 cls=$2 jargs=${3:-}
  local log="$L/$lab.ant.log"
  rm -f "$L/$lab.stage4.out"
  echo "+ ant testsome -Dtest.name=$cls -Dtest.jvm.args=\"$jargs -Dstage4.out=$L/$lab.stage4.out\"  > $log" >> "$CL"
  ant -Dlocal.repository=$W/m2 testsome -Dtest.name=$cls -Dtest.jvm.args="$jargs -Dstage4.out=$L/$lab.stage4.out" -Dtest.timeout=1800000 > "$log" 2>&1 < /dev/null
  local rc=$?
  for x in build/test/output/TEST-$cls*.xml; do [ -e "$x" ] && cp "$x" "$L/$lab.junit.xml"; done
  say "$lab exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$log") $(grep -m1 -o 'Total time: .*' "$log")"
  grep -h '^STAGE4 [0-9]* RESULT' "$L/$lab.stage4.out" 2>/dev/null | sed "s/^/  $lab /" >> "$S"
}
T=org.apache.cassandra.db.commitlog.CDCAllowanceTest
if [ "$what" = instrument ]; then
  cmd ant -Dlocal.repository=$W/m2 build-test && say "build-test with CDCAllowanceTest: BUILD SUCCESSFUL" || { say "build-test FAILED"; exit 1; }
  run upstream org.apache.cassandra.db.commitlog.CommitLogSegmentManagerCDCTest
  run helper $T "-Dstage4.cdc.scenario=helper"
  run block-s4 $T "-Dstage4.cdc.scenario=block -Dstage4.cdc.s=4"
fi
if [ "$what" = run ]; then
  for s in 8 16 32; do run block-s$s $T "-Dstage4.cdc.scenario=block -Dstage4.cdc.s=$s"; done
  for s in 8 16 32; do run nonblock-s$s $T "-Dstage4.cdc.scenario=nonblock -Dstage4.cdc.s=$s"; done
  run ctl-plain $T "-Dstage4.cdc.scenario=ctl-plain"
  run ctl-1024 $T "-Dstage4.cdc.scenario=ctl-1024"
  run helper $T "-Dstage4.cdc.scenario=helper"
fi
d=$(ps -eo command | grep '[C]assandraDaemon'); say "final CassandraDaemon processes: ${d:-none}"
say "end $(date '+%Y-%m-%dT%H:%M:%S%z')"
