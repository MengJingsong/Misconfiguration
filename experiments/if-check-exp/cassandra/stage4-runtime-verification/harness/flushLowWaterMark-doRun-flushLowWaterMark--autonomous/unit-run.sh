#!/usr/bin/env bash
# usage: bash unit-run.sh <label> handshake|sweep
#   Unit tier (B2) of flushLowWaterMark-doRun-flushLowWaterMark--autonomous (frozen sha256 f754e36f...).
#   handshake = the step-1 check (TCP proxy vs fallback, amendment A1); sweep = run 1 (B2e steps 2-5).
#   Copies FlushWaterMarkProbeTest.java into ~/cassandra-flw/test/unit/org/apache/cassandra/net/, runs ant testsome with
#   -Dtest.timeout=1800000 (A1) and -Dstage4.csv, keeps the ant log, the junit XML and the CSV under
#   ~/stage4-logs/flw/<label>/, removes the test file, and checks no test JVM / listener is left (B2e step 5).
set -uo pipefail
label=${1:?label}; what=${2:?handshake|sweep}
H=$(cd "$(dirname "$0")" && pwd)
C=${CASSANDRA_HOME:-$HOME/cassandra-flw}
L=$HOME/stage4-logs/flw/$label
mkdir -p "$L"
exec > >(tee -a "$L/unit-run.log") 2>&1
echo "=== $(date -u +%FT%TZ) $(date +%s%3N) unit-run $label $what clone $C harness $H"
md5sum "$H"/* | tee "$L/harness-md5.txt"
git -C "$C" rev-parse HEAD; git -C "$C" status --short
T=$C/test/unit/org/apache/cassandra/net/FlushWaterMarkProbeTest.java
cp "$H/FlushWaterMarkProbeTest.java" "$T"
rm -f "$L/unit.csv"
cd "$C"
set -x
ant testsome -Dtest.name=org.apache.cassandra.net.FlushWaterMarkProbeTest -Dtest.methods=$what -Dtest.timeout=1800000 \
    "-Dtest.jvm.args=-Dstage4.csv=$L/unit.csv" > "$L/ant-$what.log" 2>&1 < /dev/null
rc=$?
set +x
echo "ant exit $rc"
cp build/test/output/TEST-org.apache.cassandra.net.FlushWaterMarkProbeTest-$what.xml "$L/" 2>/dev/null || ls build/test/output | grep FlushWater
grep -E 'STAGE4|PROBE|Tests run|BUILD|FAILED|Exception' "$L/ant-$what.log" | head -80
rm -f "$T"
rm -rf build/test/classes/org/apache/cassandra/net/FlushWaterMarkProbeTest*.class
git -C "$C" status --short
echo "--- leftovers"
ps -eo pid,args | grep '[F]lushWaterMarkProbeTest' || echo "no test JVM"
ss -ltnp 2>/dev/null | grep -E ':7012 ' || echo "no listener on 7012"
echo "=== end $(date -u +%FT%TZ) rc=$rc"
exit $rc
