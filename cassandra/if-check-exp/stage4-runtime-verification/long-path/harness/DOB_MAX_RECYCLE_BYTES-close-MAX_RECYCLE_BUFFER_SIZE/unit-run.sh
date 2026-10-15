#!/usr/bin/env bash
# Unit tier of DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE (case 9c/9e). One JVM per value.
# usage (on the measured node): unit-run.sh [instrument|upstream|harness|all]
# output: ${STAGE4_LOGROOT:-~/stage4-logs/dob}/unit/ ; CASSANDRA_HOME selects the clone (default ~/cassandra-run1).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=${STAGE4_LOGROOT:-$HOME/stage4-logs/dob}/unit
what=${1:-all}
BM=$C/build/lib/jars/byteman-4.0.20.jar
T=org.apache.cassandra.io.util.DobRecycleTest
mkdir -p "$L"; cp "$H/DobRecycleTest.java" "$C/test/unit/org/apache/cassandra/io/util/"
cd "$C"
echo "clone $C $(git rev-parse --short HEAD) $(git describe --tags); $(date '+%F %T %Z'); md5 $(md5sum "$H/DobRecycleTest.java" | cut -c1-12)"
run() {  # tag, jvm args
  local tag=$1; shift
  rm -f "${L:?}/${tag:?}.out"
  ant testsome -Dtest.name=$T "-Dtest.jvm.args=$* -Dstage4.out=$L/$tag.out" > "$L/$tag.ant.log" 2>&1 < /dev/null
  local rc=$?
  cp build/test/output/TEST-$T.xml "$L/TEST-$tag.xml" 2>/dev/null || true
  echo "$tag exit=$rc checks=$(grep -c '^STAGE4 check' "$L/$tag.out" 2>/dev/null) mismatches=$(grep -c 'MISMATCH' "$L/$tag.out" 2>/dev/null) $(grep -m1 -o 'Tests run: [^<]*' "$L/$tag.ant.log")"
}
if [ "$what" = instrument ]; then
  rm -f "${L:?}/instrument-ledger.txt"
  run instrument "-javaagent:$BM=script:$H/dob-ledger.btm -Dstage4.ledger.out=$L/instrument-ledger.txt -XX:MaxDirectMemorySize=1g"
  echo "ledger lines $(wc -l < "$L/instrument-ledger.txt" 2>/dev/null)"
  exit 0
fi
if [ "$what" = upstream ] || [ "$what" = all ]; then
  U=org.apache.cassandra.io.util.DataOutputTest
  ant testsome -Dtest.name=$U > "$L/upstream.ant.log" 2>&1 < /dev/null
  echo "upstream DataOutputTest exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")"
fi
if [ "$what" = harness ] || [ "$what" = all ]; then
  for v in 262144 4194304 64; do run "L$v" "-Dcassandra.dob_max_recycle_bytes=$v -XX:MaxDirectMemorySize=1g"; done
  run Ldefault "-XX:MaxDirectMemorySize=1g"
  run onheap "-Dcassandra.dob.allocate_type=onheap -XX:MaxDirectMemorySize=1g"
  run U10-1MiB "-Dcassandra.dob_max_recycle_bytes=1MiB -Dstage4.expect_init_failure=true"
  run U10-heap "-Dcassandra.dob.allocate_type=heap -Dstage4.expect_init_failure=true"
fi
