#!/usr/bin/env bash
# usage: unit-run.sh <label> <OFF_HEAP|ON_HEAP> <knob-MB|default> [heap=10g] [direct=6g]   (case B2a, B2e steps 3-6)
# Runs Trie2GbLimitProbeTest in one JVM through the plain java launcher with the build classpath of ~/cassandra-run1 (see the
# results file's runbook defect D1 for why not "ant testsome"). Output: $OUT/<label>.{out,log}.
set -uo pipefail
label=$1; type=$2; knob=$3; heap=${4:-10g}; direct=${5:-6g}
C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; OUT=${OUT:-$HOME/stage4-logs/trie2gb/run1/unit}; mkdir -p "$OUT"
CP="$C/build/test/classes:$C/build/classes/main:$C/build/classes/thrift:$C/build/classes/stress:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
KN=(); [ "$knob" != default ] && KN=("-Dcassandra.memtable.row_overhead_size=$knob")
rm -f "$OUT/$label.out"
echo "== $label type=$type knob=$knob heap=$heap direct=$direct $(date -u +%FT%TZ)" | tee "$OUT/$label.log"
set -x
java -Xmx$heap -XX:MaxDirectMemorySize=$direct -XX:NativeMemoryTracking=summary "${KN[@]}" \
  -Dprobe.type=$type -Dprobe.out="$OUT/$label.out" -Dprobe.nmt=true \
  -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/storage \
  -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.db.tries.Trie2GbLimitProbeTest 2>&1 | tee -a "$OUT/$label.log" | grep -v '^PROBE' | tail -20
set +x
echo "== exit ${PIPESTATUS[0]} $(date -u +%FT%TZ)" | tee -a "$OUT/$label.log"
