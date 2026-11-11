#!/usr/bin/env bash
# usage: unit-run.sh <label> <OFF_HEAP|ON_HEAP> <knob|default> <fill true|false> [extra -D args...]    (case B2a, B2e)
# Runs RowOverheadThresholdProbeTest in one JVM through the plain java launcher with the run copy's build classpath (-Xmx10g,
# MaxDirectMemorySize 6g). Same launcher as the trie_2gb harness (ant testsome appends a smaller heap). Output: $OUT/<label>.{out,log}.
set -uo pipefail
label=$1; type=$2; knob=$3; fill=$4; shift 4
C=${CASSANDRA_HOME:-$HOME/c4-ros}; OUT=${OUT:-$HOME/stage4-logs/ros/run1/unit}; mkdir -p "$OUT" $HOME/stage4-tmp/ros
CP="$C/build/test/classes:$C/build/classes/main:$C/build/classes/thrift:$C/build/classes/stress:$C/build/lib/jars/*:$C/build/test/lib/jars/*:$C/lib/*"
KN=(); [ "$knob" != default ] && KN=("-Dcassandra.memtable.row_overhead_size=$knob")
grep -E "^--(add|illegal)" "$C/conf/jvm11-server.options" > "$OUT/jvm11-opens.args"   # the node's own module flags (DatabaseDescriptor/FileUtils need them)
rm -f "$OUT/$label.out"
echo "== $label type=$type knob=$knob fill=$fill extra=$* $(date -u +%FT%TZ)" | tee "$OUT/$label.log"
set -x
java @"$OUT/jvm11-opens.args" -Xmx10g -XX:MaxDirectMemorySize=6g "${KN[@]}" "$@" \
  -Dprobe.type=$type -Dprobe.fill=$fill -Dprobe.out="$OUT/$label.out" \
  -Dcassandra.config=file://$C/conf/cassandra.yaml -Dcassandra.storagedir=$HOME/stage4-tmp/ros/storage \
  -cp "$CP" org.junit.runner.JUnitCore org.apache.cassandra.db.tries.RowOverheadThresholdProbeTest 2>&1 | tee -a "$OUT/$label.log" | grep -v '^PROBE' | tail -12
set +x
echo "== exit ${PIPESTATUS[0]} $(date -u +%FT%TZ)" | tee -a "$OUT/$label.log"
