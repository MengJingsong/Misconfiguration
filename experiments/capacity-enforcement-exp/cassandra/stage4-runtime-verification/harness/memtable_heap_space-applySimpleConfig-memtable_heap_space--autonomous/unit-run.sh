#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-24) of memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.
# usage: unit-run.sh     clone: $C (default $W/cassandra-run2)   output: $W/logs/memtable_heap_space-applySimpleConfig/unit/
# Needs: source ~/Library/Caches/stage4/env.sh. One ant testsome (one forked JVM) per test class.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run2}; L=$W/logs/memtable_heap_space-applySimpleConfig/unit
mkdir -p "$L"; rm -f "$L"/*
pgrep -f CassandraDaemon >/dev/null && { echo "a CassandraDaemon is running; stop"; exit 1; }
T=$C/test/unit/org/apache/cassandra/utils/memory
cp "$H"/MemtableHeapCapTest.java "$H"/MemtableHeapSpaceZeroTest.java "$H"/MemtableHeapSpaceDefaultTest.java "$T/"
cd "$C"; { echo "date $(date '+%F %T %z')"; echo "clone $C: $(git describe --tags) $(git rev-parse HEAD)";
  echo "harness sha256:"; shasum -a 256 "$H"/*.java; } | tee "$L/summary.txt"
run() { # <class>
  echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.$1 -Dtest.jvm.args=-Dstage4.out=$L/stage4.out" >> "$L/commands.log"
  ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.$1 -Dtest.jvm.args="-Dstage4.out=$L/stage4.out" > "$L/ant-$1.log" 2>&1
  echo "$1: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$1.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"
  cp build/test/output/TEST-org.apache.cassandra.utils.memory.$1*.xml "$L/" 2>/dev/null; }
run MemtableHeapCapTest
run MemtableHeapSpaceZeroTest
run MemtableHeapSpaceDefaultTest
echo "STAGE4 lines: $(grep -c '^STAGE4' "$L/stage4.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
pgrep -f CassandraDaemon >/dev/null && echo "WARNING: CassandraDaemon running after unit tier" | tee -a "$L/summary.txt"
echo "done $(date '+%F %T %z')" | tee -a "$L/summary.txt"
