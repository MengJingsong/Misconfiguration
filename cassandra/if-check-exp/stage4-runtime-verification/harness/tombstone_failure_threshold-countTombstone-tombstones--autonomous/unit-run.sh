#!/usr/bin/env bash
# Unit tier (B2) of tombstone_failure_threshold-countTombstone-tombstones--autonomous (frozen sha256 9e62de3a...).
# usage (on the run node): bash unit-run.sh [run-name] [shakedown]      output: ~/stage4-logs/tft/<run-name>/unit/
#  B2e step 1: df -h ~; step 2: copy the test (R1/R2 applied) into the clone; step 3: ant testsome; step 4: collect
#  build/test/tft-unit.tsv and the TFT lines; step 5: clean up (test file, tsv, build/test/cassandra; no junit JVM left).
#  "shakedown" (instrument check, not a reading) runs a copy renamed ...ShakedownTest with N = 300 and T scaled by 1/100.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-tft}; RUN=${1:-run1}; MODE=${2:-}
CLS=TombstoneFailureThresholdMemoryTest
L=$HOME/stage4-logs/tft/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/db
if [ "$MODE" = shakedown ]; then
  NAME=${CLS/Test/ShakedownTest}
  sed -e "s/class $CLS/class $NAME/" -e 's/N = 30_000/N = 300/' -e 's/{ 1_000, 10_000, 20_000, N - 1, N, 100_000, Integer.MAX_VALUE }/{ 10, 100, 200, N - 1, N, 1_000, Integer.MAX_VALUE }/' \
      -e 's#build/test/tft-unit.tsv#build/test/tft-unit-shakedown.tsv#' "$H/$CLS.java" > "$D/$NAME.java"
  grep -q 'N = 300;' "$D/$NAME.java" || { say "shakedown sed failed"; exit 1; }
  TSV=build/test/tft-unit-shakedown.tsv
else
  NAME=$CLS; cp "$H/$CLS.java" "$D/$NAME.java"; TSV=build/test/tft-unit.tsv
fi
rm -rf build/test/cassandra "$TSV" build/test/output/TEST-org.apache.cassandra.db.$NAME*.xml
t0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.db.$NAME > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp "$TSV" "$L/tft-unit.tsv" 2>/dev/null || say "NO tsv produced"
cp build/test/output/TEST-org.apache.cassandra.db.$NAME*.xml "$L/" 2>/dev/null || true
cp build/test/logs/_jdk11/TEST-org.apache.cassandra.db.$NAME.log "$L/test.log" 2>/dev/null || true
grep -o 'TFT [0-9].*' "$L"/TEST-*.xml "$L/ant.log" 2>/dev/null | sed 's/^[^:]*://' | sort -u > "$L/tft-lines.txt"
say "TFT lines: $(wc -l < "$L/tft-lines.txt"); tsv rows: $(($(wc -l < "$L/tft-unit.tsv" 2>/dev/null || echo 1) - 1))"
sed 's/^/  /' "$L/tft-unit.tsv" | tee -a "$S"
# B2e step 5: clean up
rm -f "$D/$NAME.java" "$TSV"; rm -rf build/test/cassandra
say "cleanup: test file removed; leftover junit JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$NAME")"
[ -s "$L/tft-unit.tsv" ] && python3 "$H/unit-analyze.py" "$L/tft-unit.tsv" ${MODE:+--shakedown} | tee -a "$S"
say "done $(date -Is)"
