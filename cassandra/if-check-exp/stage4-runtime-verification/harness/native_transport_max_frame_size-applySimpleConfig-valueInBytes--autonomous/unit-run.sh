#!/usr/bin/env bash
# Unit tier (B2, amended 2026-10-24) of native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.
# usage: unit-run.sh [instrument]   (instrument: compile the classes and run upstream ProtocolErrorTest as a known-answer check)
#   clone: $C (default $W/cassandra-run5)   output: $W/logs/native_transport_max_frame_size-applySimpleConfig/unit/
# Needs: source ~/Library/Caches/stage4/env.sh. One ant testsome (one forked JVM) per class, in the B2e order.
set -uo pipefail
MODE=${1:-run}; H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run5}; L=$W/logs/native_transport_max_frame_size-applySimpleConfig/unit
[ "$MODE" = instrument ] && L=$L-instrument
mkdir -p "$L"; rm -f "$L"/*
ps -eo command | grep -q '[C]assandraDaemon' && { echo "a CassandraDaemon is running; stop"; exit 1; }
D=$C/test/unit/org/apache/cassandra/transport
cp "$H"/FrameCapBase.java "$H"/FrameCap1MiBTest.java "$H"/FrameCap4MiBTest.java "$H"/FrameCapDefaultTest.java "$H"/FrameCap2048MiBTest.java "$D/"
cd "$C"; { echo "date $(date '+%F %T %z')"; echo "clone $C: $(git describe --tags) $(git rev-parse HEAD)";
  echo "harness sha256:"; shasum -a 256 "$H"/*.java; } | tee "$L/summary.txt"
nb=""; TESTS="FrameCap1MiBTest FrameCap4MiBTest FrameCapDefaultTest FrameCap2048MiBTest"; [ "$MODE" = instrument ] && TESTS=ProtocolErrorTest
for T in $TESTS; do
  echo "+ ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.transport.$T $nb -Dtest.jvm.args=-Dstage4.out=$L/stage4.out" >> "$L/commands.log"
  ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.transport.$T $nb -Dtest.jvm.args="-Dstage4.out=$L/stage4.out" > "$L/ant-$T.log" 2>&1
  echo "$T: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$T.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"
  cp build/test/output/TEST-org.apache.cassandra.transport.$T*.xml "$L/" 2>/dev/null
  nb="-Dno-build-test=true"
done
echo "STAGE4 lines: $(grep -c '^STAGE4' "$L/stage4.out" 2>/dev/null || echo 0)" | tee -a "$L/summary.txt"
ps -eo command | grep -q '[C]assandraDaemon' && echo "WARNING: CassandraDaemon running after unit tier" | tee -a "$L/summary.txt"
echo "done $(date '+%F %T %z')" | tee -a "$L/summary.txt"
