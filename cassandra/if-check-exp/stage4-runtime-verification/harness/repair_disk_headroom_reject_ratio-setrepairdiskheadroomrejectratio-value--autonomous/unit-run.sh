#!/usr/bin/env bash
# Unit tier of repair_disk_headroom_reject_ratio-setrepairdiskheadroomrejectratio-value--autonomous (amended 2026-10-27).
# Copied from the closed harness ...verifyDiskHeadroomThreshold-rejectRatio--guided/unit-run.sh; adds HeadroomSetterRangeTest (mode 'setter').
# usage (on the measured node): CASSANDRA_HOME=~/cassandra-run4 unit-run.sh [upstream|harness|setter|all]   output: ${STAGE4_LOGROOT:-~/s4b-logs/hdr2}/unit/
# CASSANDRA_HOME selects the clone (default ~/cassandra-run1).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run4}; L=${STAGE4_LOGROOT:-$HOME/s4b-logs/hdr2}/unit
what=${1:-all}
mkdir -p "$L" "$C/test/unit/org/apache/cassandra/service/disk/usage"
cp "$H/RepairHeadroomCheckTest.java" "$C/test/unit/org/apache/cassandra/service/"
cp "$H/HeadroomSetterRangeTest.java" "$C/test/unit/org/apache/cassandra/service/"
cp "$H/RepairHeadroomVerbTest.java" "$C/test/unit/org/apache/cassandra/repair/"
cp "$H/DiskUsageOperandTest.java" "$C/test/unit/org/apache/cassandra/service/disk/usage/"
cd "$C"
echo "clone $C $(git rev-parse --short HEAD) $(git describe --tags); $(date '+%F %T %Z'); md5 $(cd "$H" && md5sum *Test.java | cut -c1-12 | tr '\n' ' ')"
run() {  # class, output tag
  local T=$1 tag=$2
  rm -f "${L:?}/${tag:?}.out"
  ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dstage4.out=$L/$tag.out" > "$L/$tag.ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$T.xml "$L/" 2>/dev/null || true
  echo "$tag exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$tag.out" 2>/dev/null) mismatches=$(grep -c 'MISMATCH' "$L/$tag.out" 2>/dev/null) $(grep -m1 -o 'Tests run: [^<]*' "$L/$tag.ant.log")"
}
if [ "$what" = upstream ] || [ "$what" = all ]; then
  run org.apache.cassandra.service.ActiveRepairServiceTest upstream-ActiveRepairServiceTest
  run org.apache.cassandra.db.guardrails.GuardrailDiskUsageTest upstream-GuardrailDiskUsageTest
fi
if [ "$what" = setter ] || [ "$what" = all ]; then
  run org.apache.cassandra.service.HeadroomSetterRangeTest S1-S2
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  run org.apache.cassandra.service.RepairHeadroomCheckTest U1-U2-U4a
  run org.apache.cassandra.repair.RepairHeadroomVerbTest U4b
  run org.apache.cassandra.service.disk.usage.DiskUsageOperandTest U3
fi
