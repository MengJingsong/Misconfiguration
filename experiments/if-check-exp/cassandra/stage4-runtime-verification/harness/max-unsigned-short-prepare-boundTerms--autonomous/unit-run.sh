#!/usr/bin/env bash
# Unit tier (B2) of max-unsigned-short-prepare-boundTerms--autonomous: one JVM per cache size, same test.
# usage: unit-run.sh [run-name] [sizes...]   tree: $CASSANDRA_HOME (default ~/s4-b9-bt/u)   output: ~/s4-b9-bt-logs/<run>/unit/
# EXPECTED: every `STAGE4 check` line ends OK; for each size the ant run reports Failures: 0, Errors: 0; summary ends "MISMATCH lines: 0".
# Stops at once if the first JVM's boundary check (cal / 65536) fails. No node is started here; a test JVM per ant call, none left running.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b9-bt/u}; RUN=${1:-run1}; shift || true
SIZES=${*:-"10 1 100"}; L=$HOME/s4-b9-bt-logs/$RUN/unit
mkdir -p "$L"
cp "$H/PrepareMarkerLimitTest.java" "$C/test/unit/org/apache/cassandra/cql3/"
cd "$C"; echo "tree $C: $(git describe --tags) $(git rev-parse --short HEAD); sizes: $SIZES; $(date -u +%FT%TZ)" | tee "$L/summary.txt"
for v in $SIZES; do
  y="$L/cassandra-$v.yaml"; grep -v '^prepared_statements_cache_size:' test/conf/cassandra.yaml > "$y"; echo "prepared_statements_cache_size: ${v}MiB" >> "$y"
  ant testsome -Dtest.name=org.apache.cassandra.cql3.PrepareMarkerLimitTest -Dtest.timeout=3000000 \
    -Dtest.jvm.args="-Dcassandra.config=file://$y -Dstage4.out=$L/run.out -Dstage4.label=c$v" </dev/null > "$L/ant-$v.log" 2>&1
  echo "c$v: ant rc=$?; $(grep -m1 'Tests run' "$L/ant-$v.log" || echo 'no Tests run line')" | tee -a "$L/summary.txt"
  if ! grep -q "STAGE4 check c$v boundary-65536-rejected .* OK" "$L/run.out" 2>/dev/null; then echo "STOP: boundary check of c$v failed or missing" | tee -a "$L/summary.txt"; break; fi
done
echo "checks: $(grep -c 'STAGE4 check' "$L/run.out"); MISMATCH lines: $(grep -c MISMATCH "$L/run.out")" | tee -a "$L/summary.txt"
