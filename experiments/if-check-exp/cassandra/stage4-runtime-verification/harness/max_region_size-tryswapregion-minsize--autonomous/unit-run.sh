#!/usr/bin/env bash
# usage: unit-run.sh <arm R1024|R256> <run-copy-dir> <case> [arg]   -> one JVM; output appended to $OUT/<arm>.out
# Compiles nothing: NativeAllocatorRegionProbe must already be in <run-copy>/build/probe (unit-all.sh does that).
set -uo pipefail
arm=$1; C=$2; shift 2
OUT=${OUT:-$HOME/stage4-logs/mrs/run1/unit}; mkdir -p "$OUT"
CP="$C/build/probe:$C/build/classes/main:$C/build/classes/thrift:$C/build/lib/jars/*:$C/lib/*"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"
echo "== $arm $* $(date -u +%FT%TZ)" >> "$OUT/$arm.out"
java @"$OUT/jvm11-opens.args" -Xmx512m -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/mrs/storage \
  -cp "$CP" org.apache.cassandra.utils.memory.NativeAllocatorRegionProbe "$@" 2>&1 | grep -E '^(READ|Exception|java\.|\s+at |Caused)' >> "$OUT/$arm.out"
echo "== rc ${PIPESTATUS[0]}" >> "$OUT/$arm.out"
