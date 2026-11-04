#!/usr/bin/env bash
# Unit tier B2 of block_packed_max_block_size-checkblocksize-blocksize--autonomous (amended 2026-10-28). usage (measured node): unit-run.sh [label]
# Arms: stock = ~/s4-b34/base; patched = ~/s4-b34/v-max28 (MAX_BLOCK_SIZE = 1 << 28, `ant jar`, readers recompiled). One JVM per cell, 3 repetitions,
# -Xmx3g (stock) and -Xmx6g (patched). Then the upstream SAICodecUtilsTest as a known answer (`ant testsome` in the base copy).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); label=${1:-run1}
L=$HOME/s4-b34/logs/maxblock/unit/$label; mkdir -p "$L"; W=$HOME/s4-b34
OPTS=$(grep -h '^--add' "$W/base/conf/jvm11-server.options" | tr '\n' ' ')
echo "unit-run $label $(date -Is) probe md5 $(md5sum "$H/BlockSizeBoundProbe.java" | cut -c1-12)" | tee "$L/summary.txt"
cell() {  # cell <arm> <heap> <rep> <args...>
  local arm=$1 heap=$2 rep=$3; shift 3
  local C=$W/base; [ $arm = patched ] && C=$W/v-max28
  local CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
  [ -d "$L/cls-$arm" ] || { mkdir -p "$L/cls-$arm"; javac -cp "$CP" -d "$L/cls-$arm" "$H/BlockSizeBoundProbe.java" 2>&1 | tee "$L/javac-$arm.log"; }
  local tag="$arm-r$rep-$(echo "$@" | tr ' ' '_')"
  java -Xmx$heap -XX:+UseSerialGC $OPTS -cp "$L/cls-$arm:$CP" org.apache.cassandra.index.sai.disk.v1.bitpack.BlockSizeBoundProbe "$@" > "$L/$tag.out" 2>&1
  echo "exit=$? $tag :: $(grep -h STAGE4 "$L/$tag.out" | cut -c1-230 | tr '\n' '|')" | tee -a "$L/summary.txt"
}
for rep in 1 2 3; do
  for arm in stock patched; do
    heap=3g; [ $arm = patched ] && heap=6g
    for bs in 32 96 64 128 16384 1048576 67108864 134217728 268435456; do
      for kind in plain mono; do cell $arm $heap $rep writer $kind $bs "$arm"; done
    done
    for bs in 32 96 64 128 16384 134217728 268435456; do cell $arm $heap $rep check $bs; done
    for bs in 99 268435456 64 128 16384; do for kind in plain mono; do cell $arm $heap $rep reader $kind $bs 1000000000; done; done
  done
done
cd $W/base && ant testsome -Dtest.name=org.apache.cassandra.index.sai.disk.v1.SAICodecUtilsTest > "$L/upstream.ant.log" 2>&1 < /dev/null
echo "upstream SAICodecUtilsTest exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")" | tee -a "$L/summary.txt"
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon" | tee -a "$L/summary.txt"
