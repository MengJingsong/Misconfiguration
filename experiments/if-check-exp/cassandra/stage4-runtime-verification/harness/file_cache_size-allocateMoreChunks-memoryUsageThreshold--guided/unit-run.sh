#!/usr/bin/env bash
# Unit tier of file_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9e unit steps 1-2, amended 2026-10-14).
# usage (on the measured node): unit-run.sh [upstream|harness|all]
# output: ${STAGE4_LOGROOT:-~/stage4-logs/fcs}/unit/ ; one summary line per test class.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=${STAGE4_LOGROOT:-$HOME/stage4-logs/fcs}/unit
what=${1:-all}
P=org.apache.cassandra.utils.memory
mkdir -p "$L"; cp "$H/BufferPoolCeilingTest.java" "$C/test/unit/org/apache/cassandra/utils/memory/"
cd "$C"
echo "clone $(git rev-parse --short HEAD) $(git describe --tags); harness md5 $(md5sum "$H/BufferPoolCeilingTest.java" | cut -c1-12); $(date '+%F %T %Z')"
if [ "$what" = upstream ] || [ "$what" = all ]; then
  U=$P.BufferPoolTest
  ant testsome -Dtest.name=$U > "$L/upstream.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$U.xml "$L/" 2>/dev/null || true
  echo "upstream BufferPoolTest exit=$rc $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")"
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  T=$P.BufferPoolCeilingTest
  rm -f "$L/harness.out"
  ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dstage4.out=$L/harness.out" > "$L/harness.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$T.xml "$L/" 2>/dev/null || true
  echo "harness BufferPoolCeilingTest exit=$rc checks=$(grep -c '^STAGE4 check' "$L/harness.out" 2>/dev/null) mismatches=$(grep -c 'MISMATCH$' "$L/harness.out" 2>/dev/null) $(grep -m1 '^STAGE4 done' "$L/harness.out" 2>/dev/null) $(grep -m1 -o 'Tests run: [^<]*' "$L/harness.ant.log")"
fi
