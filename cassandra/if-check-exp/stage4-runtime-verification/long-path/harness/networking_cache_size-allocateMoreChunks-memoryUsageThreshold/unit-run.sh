#!/usr/bin/env bash
# Unit tier of networking_cache_size-allocateMoreChunks-memoryUsageThreshold (case 9c/9e): copies the two harness tests into the
# clone and runs U1 (upstream BufferPoolTest, BufferPoolAllocatorTest), U2-U3 (NetworkingPoolCeilingTest), U4 (NetworkingPoolConfigTest),
# one ant call (one JVM) each.
# usage: unit-run.sh [suffix]   clone: $CASSANDRA_HOME (default ~/cassandra-run3)   output: ~/stage4-logs/ncs/unit[-suffix]/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run3}; L=$HOME/stage4-logs/ncs/unit${1:+-$1}
mkdir -p "$L"; rm -f "$L/run.out" "$L/summary.txt"
cp "$H/NetworkingPoolCeilingTest.java" "$C/test/unit/org/apache/cassandra/utils/memory/"
cp "$H/NetworkingPoolConfigTest.java" "$C/test/unit/org/apache/cassandra/net/"
cd "$C"
echo "clone $C: $(git describe --tags) $(git rev-parse --short HEAD)" | tee "$L/summary.txt"
for t in org.apache.cassandra.utils.memory.BufferPoolTest org.apache.cassandra.net.BufferPoolAllocatorTest \
         org.apache.cassandra.utils.memory.NetworkingPoolCeilingTest org.apache.cassandra.net.NetworkingPoolConfigTest; do
  n=${t##*.}
  ant testsome -Dtest.name=$t -Dtest.jvm.args="-Dstage4.out=$L/run.out" > "$L/ant-$n.log" 2>&1
  rc=$?
  echo "$n: ant rc=$rc; $(grep -m1 'Tests run' "$L/ant-$n.log" || echo 'no Tests run line'); $(grep -c 'BUILD FAILED' "$L/ant-$n.log") BUILD FAILED" | tee -a "$L/summary.txt"
done
echo "checks: $(grep -c 'STAGE4 check' "$L/run.out" 2>/dev/null || echo 0); MISMATCH lines: $(grep -c MISMATCH "$L/run.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
