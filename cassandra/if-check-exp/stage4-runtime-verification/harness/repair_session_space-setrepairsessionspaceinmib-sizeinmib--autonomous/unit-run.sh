#!/usr/bin/env bash
# Unit tier of repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous (amended 2026-10-27). Copied from the closed harness
# repair_session_space-split-maxsize--guided/unit-run.sh; adds the mode "setter" (SessionSpaceSetterTest).
# usage (on the measured node): CASSANDRA_HOME=~/cassandra-run4 unit-run.sh [upstream|harness|setter|instrument|all]     output: ~/s4b-logs/rss2/unit[-<mode>]/
#   upstream    MerkleTreeTest, ValidatorTest (one ant testsome each)
#   harness     RepairSessionSpaceTreeTest; STAGE4 lines in harness.out, summary.txt
#   instrument  RepairSessionSpaceTreeTest#u3Derivation with split-trace.btm attached: the trace lines must appear (not a reading)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run4}
what=${1:-all}
L=$HOME/s4b-logs/rss2/unit; [ "$what" = instrument ] && L=$HOME/s4b-logs/rss2/unit-instrument
mkdir -p "$L"; S=$L/summary.txt; : > "$S"
cp "$H/RepairSessionSpaceTreeTest.java" "$H/SessionSpaceSetterTest.java" "$C/test/unit/org/apache/cassandra/repair/"
cd "$C"
say() { echo "$*" | tee -a "$S"; }
say "unit-run $what $(date -Is) clone $(git describe --tags) $(git rev-parse --short HEAD) harness md5 $(md5sum "$H/RepairSessionSpaceTreeTest.java" | cut -c1-12)"
run() {   # run <class> [extra ant args...]
  local cls=$1; shift
  ant testsome -Dtest.name=$cls "$@" > "$L/$(basename ${cls//./_}).ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$cls*.xml "$L/" 2>/dev/null || true
  say "$cls exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/$(basename ${cls//./_}).ant.log")"
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  run org.apache.cassandra.utils.MerkleTreeTest
  run org.apache.cassandra.repair.ValidatorTest
  run org.apache.cassandra.service.ActiveRepairServiceTest
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  rm -f "$L/harness.out"
  run org.apache.cassandra.repair.RepairSessionSpaceTreeTest -Dtest.jvm.args="-Dstage4.out=$L/harness.out"
  say "STAGE4 checks: $(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok$' "$L/harness.out" 2>/dev/null) MISMATCH: $(grep -c 'MISMATCH' "$L/harness.out" 2>/dev/null)"
  grep 'MISMATCH' "$L/harness.out" 2>/dev/null | tee -a "$S"
fi
if [ "$what" = setter ] || [ "$what" = all ]; then
  rm -f "$L/setter.out"
  run org.apache.cassandra.repair.SessionSpaceSetterTest -Dtest.jvm.args="-Dstage4.out=$L/setter.out"
  say "SETTER checks: $(grep -c '^STAGE4 check' "$L/setter.out" 2>/dev/null) ok: $(grep -c '^STAGE4 check.* ok$' "$L/setter.out" 2>/dev/null) MISMATCH: $(grep -c 'MISMATCH' "$L/setter.out" 2>/dev/null)"
  grep 'MISMATCH' "$L/setter.out" 2>/dev/null | tee -a "$S"
fi
if [ "$what" = instrument ]; then
  rm -f "$L/harness.out" "$L/split.trace"
  run org.apache.cassandra.repair.RepairSessionSpaceTreeTest -Dtest.methods=u3Derivation \
    -Dtest.jvm.args="-javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:$H/split-trace.btm -Dorg.jboss.byteman.verbose=false -Dstage4.trace=$L/split.trace -Dstage4.out=$L/harness.out"
  for pat in 'split refused' 'split calls=' 'samples='; do say "trace '$pat': $(grep -c "$pat" "$L/split.trace" 2>/dev/null)"; done
  say "trace 'split toodeep': $(grep -c 'split toodeep' "$L/split.trace" 2>/dev/null)"
  grep -h -i 'byteman.*\(error\|exception\)\|Rule.*failed\|TypeException' "$L"/*.ant.log | head -5 | tee -a "$S"
fi
