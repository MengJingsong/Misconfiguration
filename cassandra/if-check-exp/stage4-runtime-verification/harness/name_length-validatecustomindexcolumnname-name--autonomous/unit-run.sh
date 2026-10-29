#!/usr/bin/env bash
# Unit tier (B2 + B2i) of name_length-validatecustomindexcolumnname-name--autonomous.
# usage: unit-run.sh [run-name]     output: ~/s4-b2-logs/<run>/unit/
# Compiles NameLengthProbeTest outside the tree, runs it through JUnitCore in two JVMs (-Xmx4g, sasi_indexes_enabled: true):
#   names (L x kind x 3 repeats) and rows (row-count control + unindexed baseline). summary.txt gets EXPECTED lines from analyze-unit.py.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); T=${CASSANDRA_HOME:-$HOME/s4-b2/c}; RUN=${1:-run1}
L=$HOME/s4-b2-logs/$RUN/unit; mkdir -p "$L/classes"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
CP="$T/build/test/classes:$T/build/classes/main:$T/build/classes/thrift:$T/build/classes/stress:$T/build/lib/jars/*:$T/build/test/lib/jars/*:$T/lib/*"
grep -E "^--(add|illegal)" "$T/conf/jvm11-server.options" > "$L/jvm11-opens.args"
JAMM=$(ls $T/build/lib/jars/jamm-*.jar | head -1)
say "unit-run $(date -Is) host $(hostname -s) tree $(git -C "$T" describe --tags) $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum NameLengthProbeTest.java unit-run.sh analyze-unit.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
javac -d "$L/classes" -cp "$CP" "$H/NameLengthProbeTest.java" > "$L/javac.log" 2>&1 || { say "COMPILE FAILED"; cat "$L/javac.log" | tee -a "$S"; exit 1; }
STORE=$HOME/s4-b2-store; mkdir -p "$STORE"
run() { local name=$1 mode=$2; local st=${STORE:?}/${RUN:?}-${name:?}; rm -rf "${st:?}"; mkdir -p "$st"
  local y=$L/cassandra-$name.yaml
  sed -e "s#build/test/cassandra/#$st/#g" -e '/^memtable_heap_space/d' -e '/^sasi_indexes_enabled/d' "$T/test/conf/cassandra.yaml" > "$y"
  printf 'memtable_heap_space: 2048MiB\nsasi_indexes_enabled: true\n' >> "$y"
  rm -f "${L:?}/${name:?}.out"; say "run $name: mode=$mode yaml=$y"
  ( cd "$T" && java @"$L/jvm11-opens.args" -javaagent:$JAMM -ea -Xmx4g -Xss256k -XX:SoftRefLRUPolicyMSPerMB=0 -Djava.io.tmpdir=$st/tmp \
    -Dcassandra.config=file://$y -Dcassandra.storagedir=$st -Dcassandra.skip_sync=true -Dcassandra.ring_delay_ms=1000 \
    -Dcassandra.tolerate_sstable_size=true -Dcassandra.memtable_row_overhead_computation_step=100 -Djava.security.egd=file:/dev/urandom \
    -Dprobe.out="$L/$name.out" -Dprobe.mode=$mode \
    -cp "$L/classes:$CP" org.junit.runner.JUnitCore org.apache.cassandra.cql3.NameLengthProbeTest > "$L/$name.junit.log" 2>&1 )
  local rc=$?; say "run $name exit $rc, $(grep -c '^STAGE4' "$L/$name.out" 2>/dev/null) STAGE4 lines; junit: $(grep -E '^(OK|Tests run)' "$L/$name.junit.log" | tr '\n' ' ')"
  rm -rf "${st:?}"; return $rc; }
run names names || { say "FAILED: names"; tail -15 "$L/names.junit.log" | tee -a "$S"; exit 1; }
python3 "$H/analyze-unit.py" "$L" names | tee -a "$S"
grep -q "^EXPECTED: boundary.* - NO" "$S" && { say "first-trigger check failed; stopping (B2g last rows)"; exit 1; }
run rows rows || { say "FAILED: rows"; tail -15 "$L/rows.junit.log" | tee -a "$S"; exit 1; }
python3 "$H/analyze-unit.py" "$L" rows | tee -a "$S"
rmdir "$STORE" 2>/dev/null
say "done $(date -Is)"
