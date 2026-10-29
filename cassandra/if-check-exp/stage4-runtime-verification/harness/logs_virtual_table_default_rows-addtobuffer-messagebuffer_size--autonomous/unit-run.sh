#!/usr/bin/env bash
# usage: unit-run.sh <copy dir> <out dir>   (case B2, 2026-10-28). Compiles the probe into <copy>/build/probe (not into the repository), then one JVM per cell.
# EXPECTED lines are printed by the checker (selfcheck.py); this script only runs and logs.
set -uo pipefail
C=${1:?copy dir}; OUT=${2:?out dir}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$C/build/probe"
CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/lib/*"
javac -cp "$CP" -d "$C/build/probe" "$H/VtableBufferProbe.java" 2>&1 | tee "$OUT/javac.log"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
run() { # label, jvm props..., -- args
  local label=$1; shift; local props=(); while [ "$1" != "--" ]; do props+=("$1"); shift; done; shift
  echo "== $label $* $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
  java @"$OUT/jvm11-opens.args" -Xms2g -Xmx2g "${props[@]}" -cp "$C/build/probe:$CP" org.apache.cassandra.db.virtual.VtableBufferProbe "$@" 2>&1 \
     | grep -E '^(STAGE4|Exception|java\.|\s+at |Caused)' | tee -a "$OUT/unit.out"
  echo "== rc ${PIPESTATUS[0]}" | tee -a "$OUT/unit.out"
}
rm -f "$OUT/unit.out"
for N in 0 1000 49999 50000 50001 120000; do run "A100-N$N" -- appender $N 100; done
for N in 50000 120000; do run "A10K-N$N" -- appender $N 10240; done
for m in 1000 50000 100000; do run "T-m$m" -Dcassandra.virtual.logs.max.rows=$m -- table 120000 100; done
run "T-m500-fallback" -Dcassandra.virtual.logs.max.rows=500 -- table 120000 100
echo "unit run finished $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
