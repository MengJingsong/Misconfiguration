#!/usr/bin/env bash
# Unit tier of CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT (case 9e unit steps 1-2).
# usage (on the measured node): unit-run.sh [upstream|harness|all] [values...]   default values: 100000 1000000 4000000 1 0
# output: ${STAGE4_LOGROOT:-~/stage4-logs/cms}/unit/ ; one summary line per JVM.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=${STAGE4_LOGROOT:-$HOME/stage4-logs/cms}/unit
what=${1:-all}; shift || true
values=${*:-100000 1000000 4000000 1 0}
T=org.apache.cassandra.db.CacheableMutationSizeTest
mkdir -p "$L"; cp "$H/CacheableMutationSizeTest.java" "$C/test/unit/org/apache/cassandra/db/"
cd "$C"
echo "clone $(git rev-parse --short HEAD) $(git describe --tags); harness md5 $(md5sum "$H/CacheableMutationSizeTest.java" | cut -c1-12); $(date '+%F %T %Z')"
if [ "$what" = upstream ] || [ "$what" = all ]; then
  U=org.apache.cassandra.utils.TeeDataInputPlusTest
  ant testsome -Dtest.name=$U > "$L/upstream.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$U.xml "$L/" 2>/dev/null || true
  echo "upstream TeeDataInputPlusTest exit=$rc $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")"
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  for v in $values; do
    rm -f "$L/$v.out"
    ant testsome -Dtest.name=$T \
      -Dtest.jvm.args="-Dcassandra.cacheable_mutation_size_limit_bytes=$v -Dstage4.expect_limit=$v -Dstage4.out=$L/$v.out" \
      > "$L/$v.ant.log" 2>&1 < /dev/null
    rc=$?
    cp build/test/output/TEST-$T.xml "$L/$v.TEST.xml" 2>/dev/null || true
    echo "L=$v exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$v.out" 2>/dev/null) mismatches=$(grep -c 'MISMATCH$' "$L/$v.out" 2>/dev/null) records-differ=$(grep -c '^STAGE4 record.* differs$' "$L/$v.out" 2>/dev/null) $(grep -m1 '^STAGE4 done' "$L/$v.out" 2>/dev/null) $(grep -m1 -o 'Tests run: [^<]*' "$L/$v.ant.log")"
  done
fi
