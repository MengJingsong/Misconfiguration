#!/usr/bin/env bash
# Unit tier of memtable_offheap_space-tryAllocate-limit (case 9e unit steps 1-2).
# usage (on the measured node): unit-run.sh      output: ~/stage4-logs/mos/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; L=$HOME/stage4-logs/mos/unit
mkdir -p "$L"; rm -f "$L/NativePoolTest.out"
cp "$H/NativePoolTest.java" "$C/test/unit/org/apache/cassandra/utils/memory/"
cd "$C"
{ echo "clone: $(git rev-parse HEAD) $(git describe --tags)"; sha256sum "$H/NativePoolTest.java" test/unit/org/apache/cassandra/utils/memory/NativePoolTest.java; } > "$L/versions.txt"
for t in NativeAllocatorTest NativePoolTest; do
  extra=""; [ "$t" = NativePoolTest ] && extra="-Dtest.jvm.args=-Dstage4.out=$L/NativePoolTest.out"
  ant testsome -Dtest.name=org.apache.cassandra.utils.memory.$t ${extra:+"$extra"} > "$L/$t.ant.log" 2>&1 < /dev/null
  rc=$?
  cp build/test/output/TEST-org.apache.cassandra.utils.memory.$t.xml "$L/" 2>/dev/null || true
  echo "$t exit=$rc $(grep -m1 'Tests run' "$L/$t.ant.log")"
done
echo "NativePoolTest STAGE4 lines: $(grep -c '^STAGE4' "$L/NativePoolTest.out" 2>/dev/null || echo 0), mismatches: $(grep -c MISMATCH "$L/NativePoolTest.out" 2>/dev/null)"
