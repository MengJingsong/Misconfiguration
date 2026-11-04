#!/usr/bin/env bash
# usage: unit-run.sh <copy dir> <out dir> [grid|check]   (case B2, 2026-10-28). Compiles the probe into <copy>/build/probe, then one JVM per cell.
# Cells: caps -1 (default), 1000, 100 x limits 1, 64, 1024 MiB, N=200000, S=1000, 3 repetitions; boundary pairs; gap test.
set -uo pipefail
C=${1:?copy dir}; OUT=${2:?out dir}; MODE=${3:-grid}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$C/build/probe" "$HOME/stage4-tmp/b34/tmp"
CP="$C/build/classes/main:$C/build/classes/thrift:$C/build/test/classes:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
javac -cp "$CP" -d "$C/build/probe" "$H/SegmentRowCapProbe.java" 2>&1 | tee "$OUT/javac.log"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
run() { # label, args...
  local label=$1; shift
  echo "== $label $* $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
  ( cd "$C" && java @"$OUT/jvm11-opens.args" -Xms3g -Xmx3g -XX:+UseSerialGC -Dprobe.tmp=$HOME/stage4-tmp/b34/tmp -Dcassandra.config=file://$C/test/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/b34/storage \
     -cp "$C/build/probe:$CP" org.apache.cassandra.index.sai.disk.v1.SegmentRowCapProbe "$@" 2>&1 ) | grep -E '^(STAGE4|Exception|java\.|\s+at |Caused)' | tee -a "$OUT/unit.out"
  echo "== rc ${PIPESTATUS[0]}" | tee -a "$OUT/unit.out"
}
if [ "$MODE" = check ]; then
  rm -f "$OUT/unit.out"
  run "check-pair-default" pair -1 0 1073741822
  run "check-small" grid 1000 64 5000 1000
  exit 0
fi
rm -f "$OUT/unit.out"
D=1073741822
for rep in 1 2 3; do
  for cap in -1 1000 100; do for L in 1 64 1024; do run "G-cap$cap-L$L-r$rep" grid $cap $L 200000 1000; done; done
done
run "P-default-0-cap" pair -1 0 $D
run "P-default-0-cap+1" pair -1 0 $((D+1))
run "P-cap1000-0-1000" pair 1000 0 1000
run "P-cap1000-0-1001" pair 1000 0 1001
run "P-gap-0-1073741823" pair -1 0 1073741823
echo "unit run finished $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
