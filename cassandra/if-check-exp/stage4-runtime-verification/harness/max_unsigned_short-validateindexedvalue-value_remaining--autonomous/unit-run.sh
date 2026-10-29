#!/usr/bin/env bash
# Unit tier (B2 + B2i) of max_unsigned_short-validateindexedvalue-value_remaining--autonomous.
# usage: unit-run.sh [run-name] [quick]     output: ~/s4-b2-logs/<run>/unit/
# Compiles IndexedValueLimitTest outside the tree, runs it through JUnitCore in separate JVMs (-Xmx4g):
#   bounds (yaml pool 2048 MiB), scale_default (2048 MiB, N=100,1000,4000), scale_pool64 (64 MiB, N=4000).
# Stops at the first failed boundary check. summary.txt gets EXPECTED lines from analyze-unit.py.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); T=${CASSANDRA_HOME:-$HOME/s4-b2/c}; RUN=${1:-run1}; MODE=${2:-main}
L=$HOME/s4-b2-logs/$RUN/unit; mkdir -p "$L/classes"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
CP="$T/build/test/classes:$T/build/classes/main:$T/build/classes/thrift:$T/build/classes/stress:$T/build/lib/jars/*:$T/build/test/lib/jars/*:$T/lib/*"
grep -E "^--(add|illegal)" "$T/conf/jvm11-server.options" > "$L/jvm11-opens.args"
JAMM=$(ls $T/build/lib/jars/jamm-*.jar | head -1)
say "unit-run $(date -Is) host $(hostname -s) tree $(git -C "$T" describe --tags) $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum IndexedValueLimitTest.java unit-run.sh analyze-unit.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
javac -d "$L/classes" -cp "$CP" "$H/IndexedValueLimitTest.java" > "$L/javac.log" 2>&1 || { say "COMPILE FAILED"; cat "$L/javac.log" | tee -a "$S"; exit 1; }
mkyaml() { # $1 = pool MiB, $2 = storage dir
  local y=$L/cassandra-$1.yaml
  sed -e "s#build/test/cassandra/#$2/#g" -e '/^memtable_heap_space/d' -e '/^sasi_indexes_enabled/d' "$T/test/conf/cassandra.yaml" > "$y"
  printf 'memtable_heap_space: %sMiB\n' "$1" >> "$y"; echo "$y"; }
run() { local name=$1 pool=$2 mode=$3 ns=$4; local st=$HOME/s4-b2-store/$RUN-$name; rm -rf "$st"; mkdir -p "$st"
  local y; y=$(mkyaml "$pool" "$st"); rm -f "$L/$name.out"
  say "run $name: mode=$mode pool=${pool}MiB N=$ns yaml=$y"
  ( cd "$T" && java @"$L/jvm11-opens.args" -javaagent:$JAMM -ea -Xmx4g -Xss256k -XX:SoftRefLRUPolicyMSPerMB=0 -Djava.io.tmpdir=$st/tmp \
    -Dcassandra.config=file://$y -Dcassandra.storagedir=$st -Dcassandra.skip_sync=true -Dcassandra.ring_delay_ms=1000 \
    -Dcassandra.tolerate_sstable_size=true -Dcassandra.memtable_row_overhead_computation_step=100 -Djava.security.egd=file:/dev/urandom \
    -Dprobe.out="$L/$name.out" -Dprobe.mode=$mode -Dprobe.ns=$ns -Dprobe.label=$name \
    -cp "$L/classes:$CP" org.junit.runner.JUnitCore org.apache.cassandra.index.internal.IndexedValueLimitTest > "$L/$name.junit.log" 2>&1 )
  local rc=$?; say "run $name exit $rc, $(grep -c '^STAGE4' "$L/$name.out" 2>/dev/null) STAGE4 lines; junit: $(grep -E '^(OK|Tests run)' "$L/$name.junit.log" | tr '\n' ' ')"
  rm -rf "$st"; return $rc; }
mkdir -p $HOME/s4-b2-store
run bounds 2048 bounds 0 || { say "FAILED: bounds (see $L/bounds.junit.log)"; tail -15 "$L/bounds.junit.log" | tee -a "$S"; exit 1; }
python3 "$H/analyze-unit.py" "$L" bounds | tee -a "$S"
grep -q "^EXPECTED: boundary.* - NO" "$S" && { say "first-trigger check failed; stopping (B2g row 2)"; exit 1; }
if [ "$MODE" = quick ]; then NS=100,1000; else NS=100,1000,4000; fi
run scale_default 2048 scale $NS || { say "FAILED: scale_default"; tail -15 "$L/scale_default.junit.log" | tee -a "$S"; exit 1; }
run scale_pool64 64 scale 4000 || { say "FAILED: scale_pool64"; tail -15 "$L/scale_pool64.junit.log" | tee -a "$S"; exit 1; }
python3 "$H/analyze-unit.py" "$L" scale | tee -a "$S"
rmdir $HOME/s4-b2-store 2>/dev/null
say "done $(date -Is)"
