#!/usr/bin/env bash
# Unit tier (B2) of prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.
# One JVM per cell: arm A = $A (unmodified copy), arm B = $B (copy with 1.1 -> 1000.0), cap in MiB, offered factor, repetition.
# usage: unit-run.sh [reps]   env A (default ~/s4-base) B (default ~/s4-psc-b)   output ~/stage4-logs/pthr/unit/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); A=${A:-$HOME/s4-base}; B=${B:-$HOME/s4-psc-b}; L=$HOME/stage4-logs/pthr/unit; REPS=${1:-3}
mkdir -p "$L"
for T in $A $B; do cp "$H/PstmtPreloadThresholdTest.java" "$T/test/unit/org/apache/cassandra/cql3/"; done
for T in $A $B; do echo "tree $T: $(git -C $T describe --tags) diff-lines=$(git -C $T diff --stat | tail -1)" | tee -a "$L/summary.txt"; done
run() { # <arm> <tree> <mib> <factor> <rep>
  local lab="$1-cap$3-f$4-r$5" y="$L/cassandra-$1-cap$3.yaml"
  grep -v '^prepared_statements_cache_size:' "$2/test/conf/cassandra.yaml" > "$y"; echo "prepared_statements_cache_size: ${3}MiB" >> "$y"
  (cd "$2" && ant testsome -Dtest.name=org.apache.cassandra.cql3.PstmtPreloadThresholdTest \
    -Dtest.jvm.args="-Dcassandra.config=file://$y -Dstage4.out=$L/run.out -Dstage4.arm=$1 -Dstage4.factor=$4 -Dstage4.rep=$5" </dev/null > "$L/ant-$lab.log" 2>&1)
  echo "$lab: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$lab.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"; }
for r in $(seq 1 $REPS); do
  for cap in 1 4 10; do for arm in A B; do
    tree=$A; [ $arm = B ] && tree=$B
    run $arm $tree $cap 3 $r
  done; done
done
for cap in 1 10; do for arm in A B; do tree=$A; [ $arm = B ] && tree=$B; run $arm $tree $cap 30 1; done; done
echo "checks: $(grep -c 'STAGE4 check' "$L/run.out"); MISMATCH: $(grep -c MISMATCH "$L/run.out")" | tee -a "$L/summary.txt"
