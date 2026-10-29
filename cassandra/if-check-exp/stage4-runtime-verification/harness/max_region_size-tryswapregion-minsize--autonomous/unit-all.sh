#!/usr/bin/env bash
# usage: unit-all.sh <arm> <run-copy-dir>: compile the probe into the run copy and run every case 3 times (fresh JVM each).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); arm=$1; C=$2
export OUT=${OUT:-$HOME/stage4-logs/mrs/run1/unit}; mkdir -p "$OUT" "$C/build/probe"; rm -f "$OUT/$arm.out"
grep -n 'MAX_REGION_SIZE = ' "$C/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java" | tee -a "$OUT/$arm.out"
javac -d "$C/build/probe" -cp "$C/build/classes/main:$C/build/lib/jars/*:$C/lib/*" "$H/NativeAllocatorRegionProbe.java" || exit 1
for rep in 1 2 3; do
  echo "#### rep $rep" >> "$OUT/$arm.out"
  for cs in "C1" "C2" "C3 102400" "C3 131072" "C3 131073" "C3 4194304" "C4 1" "C4 10" "C4 100" "Z" "P1"; do
    "$H/unit-run.sh" "$arm" "$C" $cs
  done
done
echo "#### done $(date -u +%FT%TZ)" >> "$OUT/$arm.out"
