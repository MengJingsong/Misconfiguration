#!/usr/bin/env bash
# usage: unit-run.sh <copy dir> <out dir> [full|check]   (case B2, 2026-10-28). One fresh JVM per run, -Xmx12g.
set -uo pipefail
C=${1:?copy dir}; OUT=${2:?out dir}; MODE=${3:-full}; H=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT" "$C/build/probe"
BASE="$C/build/probe:$C/build/classes/main:$C/build/classes/thrift:$C/build/test/classes:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
javac -cp "$BASE" -d "$C/build/probe" "$H/LeafCountProbe.java" 2>&1 | tee "$OUT/javac.log"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
run() { # label B M N
  echo "== $1 $* $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
  ( cd "$C" && java @"$OUT/jvm11-opens.args" -Xms12g -Xmx12g -XX:+UseSerialGC -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=$HOME/stage4-tmp/b34 \
     -Dcassandra.config=file://$C/test/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/b34/storage2 \
     -cp "$BASE" org.apache.cassandra.index.sai.disk.v1.bbtree.LeafCountProbe "$@" 2>&1 ) | grep -E '^(STAGE4|Exception|java\.|\s+at |Caused|Error)' | head -30 | tee -a "$OUT/unit.out"
  echo "== rc ${PIPESTATUS[0]}" | tee -a "$OUT/unit.out"
}
if [ "$MODE" = check ]; then rm -f "$OUT/unit.out"; run check-1MiB-L-1 1048576 1 L-1; run check-1MiB-L 1048576 1 L; exit 0; fi
rm -f "$OUT/unit.out"
run A-B24-M1024-N50e6 24 1024 50000000
run Ap-B16-M1024-N50e6 16 1024 50000000
for rep in 1 2 3; do run "C-B1MiB-L-1-r$rep" 1048576 1 L-1; run "B-B1MiB-L-r$rep" 1048576 1 L; done
run "C5-B1MiB-L-5" 1048576 1 L-5
for B in 262144 4096; do run "C-B$B-L-1" $B 1 L-1; run "B-B$B-L" $B 1 L; done
run "CTL-B24-M1024-N1e6" 24 1024 1000000
run "CTL-B24-M1-N1e6" 24 1 1000000
echo "unit run finished $(date -u +%FT%TZ)" | tee -a "$OUT/unit.out"
