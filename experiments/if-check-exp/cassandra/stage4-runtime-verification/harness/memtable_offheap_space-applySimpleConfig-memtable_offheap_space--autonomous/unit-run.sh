#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-24) of memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.
# usage: unit-run.sh     clone: $C (default $W/cassandra-run3)   output: $W/logs/memtable_offheap_space-applySimpleConfig/unit/
# Needs: source ~/Library/Caches/stage4/env.sh. One ant testsome (one forked JVM) for the one test class.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run3}; L=$W/logs/memtable_offheap_space-applySimpleConfig/unit
mkdir -p "$L"; rm -f "$L"/*
ps -eo command | grep -q '[C]assandraDaemon' && { echo "a CassandraDaemon is running; stop"; exit 1; }
cp "$H"/MemtableOffHeapCapTest.java "$C/test/unit/org/apache/cassandra/utils/memory/"
cd "$C"; { echo "date $(date '+%F %T %z')"; echo "clone $C: $(git describe --tags) $(git rev-parse HEAD)";
  echo "harness sha256:"; shasum -a 256 "$H"/MemtableOffHeapCapTest.java; } | tee "$L/summary.txt"
echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.MemtableOffHeapCapTest -Dtest.jvm.args=-Dstage4.out=$L/stage4.out" >> "$L/commands.log"
ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.MemtableOffHeapCapTest -Dtest.jvm.args="-Dstage4.out=$L/stage4.out" > "$L/ant-MemtableOffHeapCapTest.log" 2>&1
echo "MemtableOffHeapCapTest: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-MemtableOffHeapCapTest.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"
cp build/test/output/TEST-org.apache.cassandra.utils.memory.MemtableOffHeapCapTest*.xml "$L/" 2>/dev/null
echo "STAGE4 lines: $(grep -c '^STAGE4' "$L/stage4.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
ps -eo command | grep -q '[C]assandraDaemon' && echo "WARNING: CassandraDaemon running after unit tier" | tee -a "$L/summary.txt"
echo "done $(date '+%F %T %z')" | tee -a "$L/summary.txt"
