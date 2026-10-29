#!/usr/bin/env bash
# Unit tier B2 of block_size-writeposting-blocksize--autonomous (amended 2026-10-28). usage (measured node): unit-run.sh [label]
# Base copy ~/s4-b34/base (copy-source.sh + ant build-test). One JVM per cell, two repetitions: blockSize 16/128/1024 x N 1000/100000/1000000 (stride 3, 1 list),
# M = 1000 lists of 50 (stride 3), the wide-stride control (stride 1000003) at N = 100000; then the upstream PostingsTest as a known answer.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); label=${1:-run1}; C=${C:-$HOME/s4-b34/base}
L=$HOME/s4-b34/logs/postings/unit/$label; mkdir -p "$L"
CP="$C/build/classes/main:$C/build/test/classes:$C/build/lib/jars/*:$C/lib/*"
OPTS=$(grep -h '^--add' "$C/conf/jvm11-server.options" | tr '\n' ' ')
rm -rf "$L/cls"; mkdir -p "$L/cls"; javac -cp "$CP" -d "$L/cls" "$H/PostingsBlockProbe.java" 2>&1 | tee "$L/javac.log"
echo "unit-run $label $(date -Is) probe md5 $(md5sum "$H/PostingsBlockProbe.java" | cut -c1-12)" | tee "$L/summary.txt"
cell() {  # cell <bs> <N> <stride> <lists> <rep>
  local T=$L/work-$1-$2-$3-$4-r$5; rm -rf "$T"; mkdir -p "$T/data" "$T/commitlog" "$T/saved_caches" "$T/hints" "$T/cdc_raw"
  cp "$C/conf/cassandra.yaml" "$T/cassandra.yaml"
  { echo "data_file_directories: [$T/data]"; echo "commitlog_directory: $T/commitlog"; echo "saved_caches_directory: $T/saved_caches"; echo "hints_directory: $T/hints"; echo "cdc_raw_directory: $T/cdc_raw"; } >> "$T/cassandra.yaml"
  mkdir -p "$T/out"
  local tag="bs$1-N$2-s$3-L$4-r$5"
  java -Xmx512m -XX:+UseSerialGC $OPTS -Dcassandra.config=file://$T/cassandra.yaml -Dcassandra.storagedir=$T -Dcassandra.logdir=$T -cp "$L/cls:$CP" \
       org.apache.cassandra.index.sai.disk.v1.postings.PostingsBlockProbe "$1" "$2" "$3" "$4" "$T/out" "$tag" > "$L/$tag.out" 2>&1
  echo "exit=$? $tag :: $(grep -h STAGE4 "$L/$tag.out" | cut -c1-260 | tr '\n' '|')" | tee -a "$L/summary.txt"
  rm -rf "$T"
}
for rep in 1 2; do
  for bs in 16 128 1024; do
    for n in 1000 100000 1000000; do cell $bs $n 3 1 $rep; done
    cell $bs 50 3 1000 $rep
    cell $bs 100000 1000003 1 $rep
  done
done
cd $C && ant testsome -Dtest.name=org.apache.cassandra.index.sai.disk.v1.postings.PostingsTest > "$L/upstream.ant.log" 2>&1 < /dev/null
echo "upstream PostingsTest exit=$? $(grep -m1 -o 'Tests run: [^<]*' "$L/upstream.ant.log")" | tee -a "$L/summary.txt"
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon" | tee -a "$L/summary.txt"
