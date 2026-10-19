#!/usr/bin/env bash
# Unit tier of coordinator_read_size_fail_threshold-shouldReject-thresholdBytes (case 9c/9e unit steps 1-8).
# usage (on the measured node): unit-run.sh [harness|upstream|all]     output: ${STAGE4_LOGROOT:-~/stage4-logs/crs}/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=${STAGE4_LOGROOT:-$HOME/stage4-logs/crs}/unit
what=${1:-harness}
mkdir -p "$L"; cp "$H/CoordinatorReadSizeGuardTest.java" "$C/test/unit/org/apache/cassandra/cql3/"
cd "$C"
echo "clone $(git rev-parse --short HEAD) $(git describe --tags); harness md5 $(md5sum "$H/CoordinatorReadSizeGuardTest.java" | cut -c1-12); $(date '+%F %T %Z')"
if [ "$what" = harness ] || [ "$what" = all ]; then
  T=org.apache.cassandra.cql3.CoordinatorReadSizeGuardTest
  rm -f "$L/harness.out"
  ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dstage4.out=$L/harness.out" > "$L/harness.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$T.xml "$L/" 2>/dev/null || true
  echo "harness exit=$rc checks=$(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) mismatches=$(grep -c 'MISMATCH' "$L/harness.out" 2>/dev/null) $(grep -m1 '^STAGE4 summary' "$L/harness.out" 2>/dev/null) $(grep -m1 -o 'Tests run: [^<]*' "$L/harness.ant.log")"
fi
if [ "$what" = upstream ] || [ "$what" = all ]; then
  U=org.apache.cassandra.distributed.test.thresholds.CoordinatorReadSizeWarningTest
  ant test-jvm-dtest-some -Dtest.name=$U > "$L/upstream.ant.log" 2>&1 < /dev/null
  rc=$?
  echo "upstream CoordinatorReadSizeWarningTest exit=$rc $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")"
fi
