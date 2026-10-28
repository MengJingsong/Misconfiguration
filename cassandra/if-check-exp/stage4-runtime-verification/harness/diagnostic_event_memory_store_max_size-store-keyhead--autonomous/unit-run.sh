#!/usr/bin/env bash
# usage: unit-run.sh <run-name>   (B2) copies the probe into ~/cassandra-run1 and runs it with ant testsome; log in ~/stage4-logs/diag/<run>/
set -uo pipefail
RUN=${1:?run name}; C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; H=$(cd "$(dirname "$0")" && pwd)
L=$HOME/stage4-logs/diag/$RUN; mkdir -p "$L"
D=$C/test/unit/org/apache/cassandra/diag/store
cp "$H/DiagnosticEventMemoryStoreCapTest.java" "$D/"
cd "$C"
{ date -u +%FT%TZ; java -version 2>&1; echo "cmd: ant testsome -Dtest.name=org.apache.cassandra.diag.store.DiagnosticEventMemoryStoreCapTest -Dtest.jvm.args='-Xmx1g'";
  ant testsome -Dtest.name=org.apache.cassandra.diag.store.DiagnosticEventMemoryStoreCapTest "-Dtest.jvm.args=-Xmx1g" </dev/null; echo "ant exit $?";
  echo "--- upstream DiagnosticEventMemoryStoreTest"; ant testsome -Dtest.name=org.apache.cassandra.diag.store.DiagnosticEventMemoryStoreTest </dev/null | tail -15; date -u +%FT%TZ; } 2>&1 | tee "$L/unit.log"
grep -h '^ *\[junit-timeout\] STAGE4\|STAGE4' "$L/unit.log" | sed 's/^ *\[junit-timeout\] //' > "$L/unit-stage4.txt"
find "$C/build/test/output" -name '*DiagnosticEventMemoryStoreCapTest*' -exec cp {} "$L/" \; 2>/dev/null
echo "readings: $L/unit-stage4.txt"
