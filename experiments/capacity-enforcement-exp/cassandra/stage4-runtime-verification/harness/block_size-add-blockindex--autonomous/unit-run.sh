#!/usr/bin/env bash
# Unit tier B2 of block_size-add-blockindex--autonomous (amended 2026-10-28). usage (measured node): unit-run.sh [run-label]   output: ~/s4-b34/logs/blockindex/unit/<label>/
# Needs the built base copy ~/s4-b34/base (copy-source.sh + ant build-test + ant jar). One JVM per (kind, size, N); two repetitions; summary.txt.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$HOME/s4-b34/base}; label=${1:-run1}
L=$HOME/s4-b34/logs/blockindex/unit/$label; mkdir -p "$L"
CP="$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*"
OPTS=$(grep -h '^--add' "$C/conf/jvm11-server.options" | tr '\n' ' ')
rm -rf "$L/cls"; mkdir -p "$L/cls"
javac -cp "$CP" -d "$L/cls" "$H/BlockPackedProbe.java" 2>&1 | tee "$L/javac.log"
echo "unit-run $label $(date -Is) probe md5 $(md5sum "$H/BlockPackedProbe.java" | cut -c1-12) base $(git -C $C describe --tags)" | tee "$L/summary.txt"
N=167772160   # 10 x 2^24
run() {  # run <kind> <bs> <N> <tag>
  local f="$L/$4.out"
  java -Xmx1g -XX:+UseSerialGC $OPTS -cp "$L/cls:$CP" org.apache.cassandra.index.sai.disk.v1.bitpack.BlockPackedProbe "$1" "$2" "$3" "$4" > "$f" 2>&1
  echo "exit=$? $4" | tee -a "$L/summary.txt"
}
for rep in 1 2; do
  for kind in plain mono; do
    for bs in 32 100; do run $kind $bs 1000 "${kind}-${bs}-invalid-r$rep"; done
    for bs in 64 128 16384 1048576 16777216; do run $kind $bs $N "${kind}-${bs}-full-r$rep"; done
    for bs in 128 16384 1048576; do run $kind $bs $((bs-1)) "${kind}-${bs}-short-r$rep"; done
  done
done
for n in 1048576 4194304 16777216; do run ctl 0 $n "ctl-$n"; done
ps -eo cmd | grep '[C]assandraDaemon' || echo "no CassandraDaemon" | tee -a "$L/summary.txt"
