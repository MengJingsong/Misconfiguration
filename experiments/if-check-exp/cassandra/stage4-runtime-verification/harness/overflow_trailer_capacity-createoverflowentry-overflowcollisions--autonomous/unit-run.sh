#!/usr/bin/env bash
# usage: unit-run.sh   (B2, as amended 2026-10-28). Compiles OverflowCapacityProbeTest against the run copy's build (javac, no change to the
# pristine tree), runs it once through JUnitCore with the java launcher and the JDK 11 module flags. Output: $OUT/unit.out, $OUT/unit.log.
set -uo pipefail
HARN=$(cd "$(dirname "$0")" && pwd)
C=${CASSANDRA_HOME:-$HOME/s4-b34/c}; OUT=${OUT:-$HOME/stage4-logs/b34/overflow/run1/unit}; mkdir -p "$OUT" "$OUT/cls" $HOME/s4-b34/tmp
CP="$C/build/test/classes:$C/build/classes/main:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
set -x
javac -nowarn -d "$OUT/cls" -cp "$CP" "$HARN/OverflowCapacityProbeTest.java" 2>&1 | tail -5
rm -f "$OUT/unit.out"
java @"$OUT/jvm11-opens.args" -Xmx1g -Dprobe.out="$OUT/unit.out" \
  -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/s4-b34/tmp/storage \
  -cp "$OUT/cls:$CP" org.junit.runner.JUnitCore org.apache.cassandra.index.sasi.disk.OverflowCapacityProbeTest 2>&1 | tee "$OUT/unit.log" | tail -15
echo "== exit ${PIPESTATUS[0]}"
grep -c PASS "$OUT/unit.out"; grep FAIL "$OUT/unit.out" || echo "no FAIL lines"
