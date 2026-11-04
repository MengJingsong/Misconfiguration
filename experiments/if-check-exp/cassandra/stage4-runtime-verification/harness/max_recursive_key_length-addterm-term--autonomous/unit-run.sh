#!/usr/bin/env bash
# usage: unit-run.sh <copy dir> <out dir> [full|check]   (case B2, 2026-10-28). Needs make-overlays.sh run first. One fresh JVM per run.
set -uo pipefail
C=${1:?copy dir}; OUT=${2:?out dir}; MODE=${3:-full}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$C/build/probe"
BASE="$C/build/probe:$C/build/classes/main:$C/build/classes/thrift:$C/build/test/classes:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
javac -cp "$BASE" -d "$C/build/probe" "$H/TrieIndexProbe.java" 2>&1 | tee "$OUT/javac.log"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
run() { # label, overlay(or -), args...
  local label=$1 ov=$2; shift 2; local cp="$BASE"; [ "$ov" != "-" ] && cp="$C/build/overlay-$ov:$BASE"
  echo "== $label overlay=$ov $* $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
  ( cd "$C" && java @"$OUT/jvm11-opens.args" -Xms2g -Xmx2g -Xss512k -XX:+UseSerialGC -Dcassandra.config=file://$C/test/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/b34/storage4 \
     -cp "$cp" org.apache.cassandra.index.sai.memory.TrieIndexProbe "$@" 2>&1 ) | grep -E '^(STAGE4|Exception|java\.|\s+at |Caused|Error)' | head -40 | tee -a "$OUT/unit.out"
  echo "== rc ${PIPESTATUS[0]}" | tee -a "$OUT/unit.out"
}
if [ "$MODE" = check ]; then
  rm -f "$OUT/unit.out"
  run check-instr-129 instr term 129 2000
  run check-instr-100 instr term 100 2000
  run check-guard - guard 1024 900 1500
  exit 0
fi
rm -f "$OUT/unit.out"
for rep in 1 2 3; do
 for ov in - z0 z1 instr zi0; do
  for L in 64 128 129 256 2048 7000; do
    run "N20000-L$L-ov$ov-r$rep" $ov term $L 20000
    run "EQ-L$L-ov$ov-r$rep" $ov term $L $((2000000 / L))
  done
 done
 run "GUARD-r$rep" - guard 1024 900 1500 7000
done
echo "unit run finished $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
