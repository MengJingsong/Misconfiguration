#!/usr/bin/env bash
# Unit tier (B2) of tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous (frozen sha256 4c289eb0..., A1-A4).
# usage: bash unit-run.sh [run-name] [shakedown]     output: ~/s4-b10-tf-logs/<run-name>/unit/
# B2e: df; copy the test into the tree; ant testsome; collect build/test/tfm-unit.tsv and the TFM lines; clean up.
# "shakedown" (instrument check, not a reading) runs a copy renamed ...ShakedownTest with N = 1200, NLIVE = 300 and T scaled.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b10-tf-src}; RUN=${1:-run1}; MODE=${2:-}
CLS=TombstoneFailureThresholdMetricsRecordingTest
L=$HOME/s4-b10-tf-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/db
if [ "$MODE" = shakedown ]; then
  NAME=${CLS/Test/ShakedownTest}
  sed -e "s/class $CLS/class $NAME/" -e 's/N = 120_000/N = 1_200/' -e 's/NLIVE = 30_000/NLIVE = 300/' \
      -e 's/{ 1_000, 10_000, 100_000, N, 200_000, Integer.MAX_VALUE }/{ 10, 100, 1_000, N, 2_000, Integer.MAX_VALUE }/' \
      -e 's/setTombstoneWarnThreshold(500)/setTombstoneWarnThreshold(5)/' \
      -e 's/LongBytesBound("1MiB")/LongBytesBound("100KiB")/' \
      -e 's#build/test/tfm-unit.tsv#build/test/tfm-unit-shakedown.tsv#' "$H/$CLS.java" > "$D/$NAME.java"
  grep -q 'N = 1_200;' "$D/$NAME.java" || { say "shakedown sed failed"; exit 1; }
  TSV=build/test/tfm-unit-shakedown.tsv
else
  NAME=$CLS; cp "$H/$CLS.java" "$D/$NAME.java"; TSV=build/test/tfm-unit.tsv
fi
rm -rf build/test/cassandra "$TSV" build/test/output/TEST-org.apache.cassandra.db.$NAME*.xml
t0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.db.$NAME > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp "$TSV" "$L/tfm-unit.tsv" 2>/dev/null || say "NO tsv produced"
cp build/test/output/TEST-org.apache.cassandra.db.$NAME*.xml "$L/" 2>/dev/null || true
cp build/test/logs/_jdk11/TEST-org.apache.cassandra.db.$NAME.log "$L/test.log" 2>/dev/null || true
grep -ho 'TFM [a-z].*' "$L"/TEST-*.xml "$L/ant.log" 2>/dev/null | sort -u > "$L/tfm-lines.txt"
say "TFM lines: $(wc -l < "$L/tfm-lines.txt"); tsv rows: $(($(wc -l < "$L/tfm-unit.tsv" 2>/dev/null || echo 1) - 1))"
sed 's/^/  /' "$L/tfm-unit.tsv" | tee -a "$S"
rm -f "${D:?}/${NAME:?}.java" "${TSV:?}"; rm -rf build/test/cassandra
say "cleanup: test file removed; leftover junit JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$NAME")"
[ -s "$L/tfm-unit.tsv" ] && python3 "$H/unit-analyze.py" "$L/tfm-unit.tsv" ${MODE:+--shakedown} | tee -a "$S"
say "done $(date -Is)"
