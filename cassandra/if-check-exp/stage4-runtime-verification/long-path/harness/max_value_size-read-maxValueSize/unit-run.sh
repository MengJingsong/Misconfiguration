#!/usr/bin/env bash
# Unit tier of max_value_size-read-maxValueSize (case 9e unit steps 1-3).
# usage (on the measured node): unit-run.sh [harness|range|upstream|all]   output: ${STAGE4_LOGROOT:-~/stage4-logs/mvs}/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=${STAGE4_LOGROOT:-$HOME/stage4-logs/mvs}/unit
what=${1:-all}
T=org.apache.cassandra.db.marshal.MaxValueSizeGuardTest
mkdir -p "$L"; cp "$H/MaxValueSizeGuardTest.java" "$C/test/unit/org/apache/cassandra/db/marshal/"
cd "$C"
echo "clone $(git rev-parse --short HEAD) $(git describe --tags); harness md5 $(md5sum "$H/MaxValueSizeGuardTest.java" | cut -c1-12); $(date '+%F %T %Z')"
if [ "$what" = harness ] || [ "$what" = all ]; then
  rm -f "$L/guard.out"
  ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dstage4.out=$L/guard.out" > "$L/guard.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$T.xml "$L/guard.TEST.xml" 2>/dev/null || true
  echo "harness exit=$rc checks=$(grep -c '^STAGE4 check' "$L/guard.out" 2>/dev/null) mismatches=$(grep -c 'MISMATCH$' "$L/guard.out" 2>/dev/null) $(tail -1 "$L/guard.out" 2>/dev/null) $(grep -m1 -o 'Tests run: [^<]*' "$L/guard.ant.log")"
fi
if [ "$what" = range ] || [ "$what" = all ]; then
  for spec in range-hi:2048MiB range-zero:0MiB; do
    IFS=: read -r label val <<< "$spec"
    y=$("$H/make-unit-yaml.sh" "$label" "$val"); rm -f "$L/$label.out"
    ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dcassandra.config=file://$y -Dstage4.out=$L/$label.out" > "$L/$label.ant.log" 2>&1 < /dev/null
    rc=$?
    cp build/test/output/TEST-$T.xml "$L/$label.TEST.xml" 2>/dev/null || true
    echo "$label exit=$rc first ConfigurationException: $(grep -h -m1 -o 'ConfigurationException: max_value_size must[^<"&]*' "$L/$label.TEST.xml" "$L/$label.ant.log" 2>/dev/null | head -1) | STAGE4 check lines: $(grep -c '^STAGE4 check' "$L/$label.out" 2>/dev/null || echo 0)"
  done
fi
if [ "$what" = upstream ] || [ "$what" = all ]; then
  U=org.apache.cassandra.io.sstable.SSTableWriterTest
  ant testsome -Dtest.name=$U > "$L/upstream.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-$U.xml "$L/" 2>/dev/null || true
  echo "upstream SSTableWriterTest exit=$rc $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log") testValueTooBigCorruption: $(grep -o '<testcase[^>]*name="testValueTooBigCorruption"[^/]*/\?>' "$L/TEST-$U.xml" 2>/dev/null | head -1)"
fi
