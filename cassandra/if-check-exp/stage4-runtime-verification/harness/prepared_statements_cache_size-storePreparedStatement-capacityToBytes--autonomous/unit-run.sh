#!/usr/bin/env bash
# Unit tier (B2) of prepared_statements_cache_size ... --autonomous: one JVM per knob value, same test.
# usage: unit-run.sh            clone: $CASSANDRA_HOME (default ~/cassandra-run3)   output: ~/stage4-logs/psc/unit/
# values: 1 2 4 8 MiB, auto (line removed -> 10 MiB at -Xmx1g), control 64 MiB with n = n(1 MiB) (B2h a)
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run3}; L=$HOME/stage4-logs/psc/unit
mkdir -p "$L"; rm -f "$L"/*
cp "$H/PreparedCacheCapTest.java" "$C/test/unit/org/apache/cassandra/cql3/"
cd "$C"; echo "clone $C: $(git describe --tags) $(git rev-parse --short HEAD)" | tee "$L/summary.txt"
mk() { # <label> <MiB|auto>
  y="$L/cassandra-$1.yaml"; grep -v '^prepared_statements_cache_size:' test/conf/cassandra.yaml > "$y"
  [ "$2" = auto ] || echo "prepared_statements_cache_size: ${2}MiB" >> "$y"; echo "$y"; }
run() { # <label> <MiB|auto> [extra jvm args]
  y=$(mk "$1" "$2")
  ant testsome -Dtest.name=org.apache.cassandra.cql3.PreparedCacheCapTest \
    -Dtest.jvm.args="-Dcassandra.config=file://$y -Dstage4.out=$L/run.out -Dstage4.label=$1 ${3:-}" > "$L/ant-$1.log" 2>&1
  echo "$1: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$1.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"; }
for v in 1 2 4 8; do run "k$v" $v; done
run kauto auto
n1=$(grep 'STAGE4 plan' "$L/run.out" | head -1 | sed 's/.*n=\([0-9]*\) .*/\1/')
run k64ctl 64 "-Dstage4.n=$n1 -Dstage4.noeviction=true"
echo "checks: $(grep -c 'STAGE4 check' "$L/run.out"); MISMATCH: $(grep -c MISMATCH "$L/run.out")" | tee -a "$L/summary.txt"
