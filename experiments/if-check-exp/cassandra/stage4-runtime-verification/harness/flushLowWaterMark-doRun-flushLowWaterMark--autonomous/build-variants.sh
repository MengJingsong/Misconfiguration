#!/usr/bin/env bash
# usage: bash build-variants.sh
#   Cluster tier (B3a, amendment A5) of flushLowWaterMark-doRun-flushLowWaterMark--autonomous (frozen sha256 f754e36f...).
#   V0 = ~/cassandra-flw (stock, built by ant build-test; its jar is rebuilt with ant jar so it is current).
#   V1..V4 = ~/cassandra-flw-p1..p4: cp -a of V0, the line-104 sed of B3a, the OutboundConnectionSettings class files
#   deleted (Ant's 1 s timestamps), ant jar. For every variant: line 104, and javap -c of the two-argument constructor from
#   the jar that bin/cassandra puts on the class path (B3h). Log: ~/stage4-logs/flw/build-variants/.
set -uo pipefail
B=$HOME/cassandra-flw
L=$HOME/stage4-logs/flw/build-variants
mkdir -p "$L"
exec > >(tee -a "$L/build-variants.log") 2>&1
echo "=== $(date -u +%FT%TZ) build-variants"
F=src/java/org/apache/cassandra/net/OutboundConnectionSettings.java
[ -e "$B/test/unit/org/apache/cassandra/net/FlushWaterMarkProbeTest.java" ] && { echo "unit test file still in V0"; exit 1; }
git -C "$B" status --short
declare -A SED=(
  [1]='104s/1 << 15, 1 << 16/1 << 10, 1 << 26/'
  [2]='104s/1 << 15, 1 << 16/1 << 25, 1 << 26/'
  [3]='104s/1 << 15, 1 << 16/(1 << 26) - (1 << 20), 1 << 26/'
  [4]='104s/1 << 15, 1 << 16/1 << 21, 1 << 22/'
)
check() {   # $1 = tree
  local t=$1
  echo "--- $t"
  sed -n 104p "$t/$F"
  grep -n 'null, null, null, null, null, null, null' "$t/$F"
  local jar; jar=$(ls -1 "$t"/build/apache-cassandra*.jar | grep -v -e javadoc -e sources)
  echo "jar: $jar ($(stat -c '%y' "$jar"))"
  javap -c -p -cp "$jar" org.apache.cassandra.net.OutboundConnectionSettings \
    | sed -n '/public org.apache.cassandra.net.OutboundConnectionSettings(org.apache.cassandra.locator.InetAddressAndPort, org.apache.cassandra.locator.InetAddressAndPort);/,/return/p' \
    | grep -E 'ldc|sipush|bipush|iconst|invokespecial' | tr -s ' '
}
( cd "$B" && ant jar < /dev/null > "$L/ant-jar-V0.log" 2>&1 ); echo "V0 ant jar rc=$? $(grep -c 'BUILD SUCCESSFUL' "$L/ant-jar-V0.log")"
check "$B"
for v in 1 2 3 4; do
  D=$HOME/cassandra-flw-p$v
  rm -rf "$D"
  cp -a "$B" "$D"
  rm -rf "$D/data" "$D/logs"
  sed -i "${SED[$v]}" "$D/$F"
  git -C "$D" diff --stat
  git -C "$D" diff > "$L/V$v.diff"
  rm -f "$D"/build/classes/main/org/apache/cassandra/net/OutboundConnectionSettings*.class
  ( cd "$D" && ant jar < /dev/null > "$L/ant-jar-V$v.log" 2>&1 ); echo "V$v ant jar rc=$? $(grep -c 'BUILD SUCCESSFUL' "$L/ant-jar-V$v.log")"
  check "$D"
done
du -sh "$B" "$HOME"/cassandra-flw-p* ; df -h /
echo "=== end $(date -u +%FT%TZ)"
