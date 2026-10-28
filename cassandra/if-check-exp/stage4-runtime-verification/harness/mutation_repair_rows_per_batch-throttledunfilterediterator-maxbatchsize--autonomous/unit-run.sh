#!/usr/bin/env bash
# usage: unit-run.sh        (case B2a/B2e as amended U1-U2) runs MutationRepairBatchProbeTest through ant testsome in $C (~/c4-mrb).
# Variants: label:valueBytes:rows:tombstone(0|1):N;N;N  (comma-separated).  Output: $OUT/{unit.out,ant.log,variants.txt}
set -uo pipefail
C=${CASSANDRA_HOME:-$HOME/c4-mrb}; OUT=${OUT:-$HOME/stage4-logs/mrb/run1/unit}; mkdir -p "$OUT"
export PROBE_OUT=$OUT/unit.out
export PROBE_VAR=${PROBE_VAR:-"b100:100:100000:0:0;2;100;1000;10000,b10:10:100000:0:0;100;1000,b1000:1000:100000:0:0;100;1000,tomb:100:20000:1:2;100;1000"}
echo "$PROBE_VAR" | tee "$OUT/variants.txt"
rm -f "$PROBE_OUT"; cd "$C"
ant testsome -Dtest.name=org.apache.cassandra.db.rows.MutationRepairBatchProbeTest </dev/null > "$OUT/ant.log" 2>&1
echo "ant rc=$?"; grep -E "Tests run|BUILD" "$OUT/ant.log" | head -3
grep -h RESULT "$PROBE_OUT"
