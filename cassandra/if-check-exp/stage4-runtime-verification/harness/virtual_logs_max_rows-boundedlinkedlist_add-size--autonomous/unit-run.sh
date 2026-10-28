#!/usr/bin/env bash
# usage: unit-run.sh <label> <mode cap|resolve> [extra -D args...]    (case B2a, B2e)
# Runs VirtualLogsMaxRowsProbeTest in one JVM (java + JUnitCore, build classpath of the run copy $C=~/c4-vlr, -Xmx1g).
# Output: $OUT/<label>.{out,log}
set -uo pipefail
label=$1; mode=$2; shift 2
C=${CASSANDRA_HOME:-$HOME/c4-vlr}; OUT=${OUT:-$HOME/stage4-logs/vlr/run1/unit}; mkdir -p "$OUT" $HOME/stage4-tmp/vlr
CP="$C/build/test/classes:$C/build/classes/main:$C/build/classes/thrift:$C/build/classes/stress:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"   # the node's own module flags (FileUtils needs them)
rm -f "$OUT/$label.out"
echo "== $label mode=$mode args=$* $(date -u +%FT%TZ)" | tee "$OUT/$label.log"
set -x
java @"$OUT/jvm11-opens.args" -Xmx1g -Dprobe.mode=$mode -Dprobe.out="$OUT/$label.out" "$@" \
  -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/vlr \
  -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.db.virtual.VirtualLogsMaxRowsProbeTest 2>&1 | tee -a "$OUT/$label.log" | grep -v '^PROBE' | tail -15
set +x
echo "== exit ${PIPESTATUS[0]} $(date -u +%FT%TZ)" | tee -a "$OUT/$label.log"
