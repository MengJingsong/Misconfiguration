#!/usr/bin/env bash
# Unit tier B2 of tokens_per_block-add-pos--autonomous (amended 2026-10-28). usage (measured node): unit-run.sh [label]
# Arms: stock = ~/s4-b34/base, v124 = ~/s4-b34/v-tpb124 (TokenTreeBuilder.java:36 = 124, `ant jar`, users touched). One JVM per cell, 3 repetitions.
# tree: N = 248, 249, 2480, 61504, 246016 (-Xmx512m); ctl: OnDiskIndexBuilder M = 1000, 100000, 1000000 (-Xmx2g, both arms). Then upstream tests as known answers.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); label=${1:-run1}; W=$HOME/s4-b34
L=$W/logs/tpb/unit/$label; mkdir -p "$L"
OPTS=$(grep -h '^--add' "$W/base/conf/jvm11-server.options" | tr '\n' ' ')
echo "unit-run $label $(date -Is) probe md5 $(md5sum "$H/TokenTreeCapProbe.java" | cut -c1-12)" | tee "$L/summary.txt"
cell() {  # cell <arm> <heap> <rep> <mode> <n>
  local arm=$1 heap=$2 rep=$3 mode=$4 n=$5
  local C=$W/base; [ $arm = v124 ] && C=$W/v-tpb124
  local CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
  [ -d "$L/cls-$arm" ] || { mkdir -p "$L/cls-$arm"; javac -cp "$CP" -d "$L/cls-$arm" "$H/TokenTreeCapProbe.java" 2>&1 | tee "$L/javac-$arm.log"; }
  local T=$L/work-$arm-$mode-$n-r$rep; rm -rf "$T"; mkdir -p "$T"/{data,commitlog,saved_caches,hints,cdc_raw}
  cp "$C/conf/cassandra.yaml" "$T/cassandra.yaml"
  { echo "data_file_directories: [$T/data]"; echo "commitlog_directory: $T/commitlog"; echo "saved_caches_directory: $T/saved_caches"; echo "hints_directory: $T/hints"; echo "cdc_raw_directory: $T/cdc_raw"; } >> "$T/cassandra.yaml"
  local tag="$arm-$mode-$n-r$rep"
  java -Xmx$heap -XX:+UseSerialGC $OPTS -Dcassandra.config=file://$T/cassandra.yaml -Dcassandra.storagedir=$T -Dcassandra.logdir=$T -cp "$L/cls-$arm:$CP" \
       org.apache.cassandra.index.sasi.disk.TokenTreeCapProbe $mode $n $tag > "$L/$tag.out" 2>&1
  echo "exit=$? $tag :: $(grep -h STAGE4 "$L/$tag.out" | cut -c1-360 | tr '\n' '|')" | tee -a "$L/summary.txt"
  rm -rf "$T"
}
for rep in 1 2 3; do
  for arm in stock v124; do
    for n in 248 249 2480 61504 246016; do cell $arm 512m $rep tree $n; done
    for m in 1000 100000 1000000; do cell $arm 2g $rep ctl $m; done
  done
done
cd $W/base
ant testsome -Dtest.name='org.apache.cassandra.index.sasi.disk.TokenTreeTest' > "$L/upstream-TokenTreeTest.ant.log" 2>&1 < /dev/null
echo "upstream TokenTreeTest exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream-TokenTreeTest.ant.log")" | tee -a "$L/summary.txt"
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon" | tee -a "$L/summary.txt"
