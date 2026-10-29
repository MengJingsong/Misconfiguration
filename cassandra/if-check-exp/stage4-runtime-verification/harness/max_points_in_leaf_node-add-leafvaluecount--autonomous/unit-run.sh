#!/usr/bin/env bash
# usage: unit-run.sh <copy dir> <out dir> [full|check]   (case B2, 2026-10-28). One fresh JVM per cell.
set -uo pipefail
C=${1:?copy dir}; OUT=${2:?out dir}; MODE=${3:-full}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$C/build/probe" "$HOME/stage4-tmp/b34/tmp1"
BASE="$C/build/probe:$C/build/classes/main:$C/build/classes/thrift:$C/build/test/classes:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
javac -cp "$BASE" -d "$C/build/probe" "$H/LeafProbe.java" 2>&1 | tee "$OUT/javac.log"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
run() { # label, args...
  local label=$1; shift
  echo "== $label $* $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
  ( cd "$C" && java @"$OUT/jvm11-opens.args" -Xms3g -Xmx3g -XX:+UseSerialGC -Dprobe.tmp=$HOME/stage4-tmp/b34/tmp1 -Dcassandra.config=file://$C/test/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/b34/storage1 \
     -cp "$BASE" org.apache.cassandra.index.sai.disk.v1.bbtree.LeafProbe "$@" 2>&1 ) | grep -E '^(STAGE4|Exception|java\.|\s+at |Caused|Error)' | grep -v 'STAGE4 KEEP' | head -40 | tee -a "$OUT/unit.out"
  echo "== rc ${PIPESTATUS[0]}" | tee -a "$OUT/unit.out"
}
if [ "$MODE" = check ]; then rm -f "$OUT/unit.out"; run check-1024 cell 1024 100000 4; run check-16 cell 16 100000 4; exit 0; fi
rm -f "$OUT/unit.out"
for M in 16 128 1024 8192 65536; do for N in 100000 1000000 4000000; do run "G-M$M-N$N-B4" cell $M $N 4; done; done
for M in 16 128 1024 8192 65536; do run "G-M$M-N1000000-B16" cell $M 1000000 16; done
run "R2-M1024-N1000000-B4" cell 1024 1000000 4
run "R3-M1024-N1000000-B4" cell 1024 1000000 4
for M in 16 1024 65536; do run "Z-M$M-N0-B4" cell $M 0 4; done
run "REJ-0" reject 0
run "REJ-MAXPLUS1" reject -1
run "CTL-alloc-1e3" alloc 1000
run "CTL-alloc-1e6" alloc 1000000
echo "unit run finished $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
