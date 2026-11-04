#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-24) of memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.
# usage: unit-run.sh     clone: $C (default $W/cassandra-run8)   output: $W/logs/memtable_cleanup_threshold-applySimpleConfig/unit/
# Needs: source ~/Library/Caches/stage4/env.sh. One ant testsome (one forked JVM) per test class (daemonInitialization once per JVM).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run8}; L=$W/logs/memtable_cleanup_threshold-applySimpleConfig/unit
mkdir -p "$L"; rm -f "$L"/*
ps -eo command | grep -q '[C]assandraDaemon' && { echo "a CassandraDaemon is running; stop"; exit 1; }
CLASSES="CleanupThresholdTest CleanupThresholdLowTest CleanupThresholdHighTest CleanupThresholdConfigTest"
for k in $CLASSES; do cp "$H/$k.java" "$C/test/unit/org/apache/cassandra/utils/memory/"; done
cd "$C"; { echo "date $(date '+%F %T %z')"; echo "clone $C: $(git describe --tags) $(git rev-parse HEAD)";
  echo "harness sha256:"; for k in $CLASSES; do shasum -a 256 "$H/$k.java"; done; } | tee "$L/summary.txt"
for k in $CLASSES; do
  echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.$k -Dtest.jvm.args=-Dstage4.out=$L/stage4.out" >> "$L/commands.log"
  ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.utils.memory.$k -Dtest.jvm.args="-Dstage4.out=$L/stage4.out" > "$L/ant-$k.log" 2>&1
  echo "$k: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$k.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"
  cp build/test/output/TEST-org.apache.cassandra.utils.memory.$k*.xml "$L/" 2>/dev/null
done
echo "STAGE4 lines: $(grep -c '^STAGE4' "$L/stage4.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
ps -eo command | grep -q '[C]assandraDaemon' && echo "WARNING: CassandraDaemon running after unit tier" | tee -a "$L/summary.txt"
echo "done $(date '+%F %T %z')" | tee -a "$L/summary.txt"
