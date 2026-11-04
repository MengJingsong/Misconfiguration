#!/usr/bin/env bash
# Unit tier (B2) of range_tombstone_list_growth_factor-growToFree-newLength--autonomous (frozen sha256 in the results file §1).
# usage (on the run node): bash unit-run.sh [run-name] [shakedown]     output: ~/stage4-logs/rtl/g/<run-name>/unit/
#  steps: df; copy the probe into the tree (/users/jason92/cassandra-rtl-g); ant testsome; collect build/test/rtl-unit-G.txt, junit XML; remove the probe; analyze.
#  "shakedown" runs a renamed copy (instrument check, not a reading) with the grid scaled down by the sed lines below.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-rtl-g}; RUN=${1:-run1}; MODE=${2:-}
CLS=RtlGrowthFactorProbeTest
L=$HOME/stage4-logs/rtl/g/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/db
if [ "$MODE" = shakedown ]; then
  NAME=${CLS/Test/ShakedownTest}
  sed -e "s/class $CLS/class $NAME/" -e 's/100_000/2_000/g' -e 's/99_999/1_999/g' -e 's/9_999/999/g' "$H/$CLS.java" > "$D/$NAME.java"
  OUT=build/test/rtl-unit-G.txt
else
  NAME=$CLS; cp "$H/$CLS.java" "$D/$NAME.java"; OUT=build/test/rtl-unit-G.txt
fi
rm -rf build/test/cassandra "$OUT" build/test/output/TEST-org.apache.cassandra.db.$NAME*.xml
t0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.db.$NAME > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp "$OUT" "$L/rtl-unit.txt" 2>/dev/null || say "NO output produced"
cp build/test/output/TEST-org.apache.cassandra.db.$NAME*.xml "$L/" 2>/dev/null || true
say "RTL lines: $(grep -c '^RTL' "$L/rtl-unit.txt" 2>/dev/null)"
rm -f "$D/$NAME.java" "$OUT"; rm -rf build/test/cassandra
say "cleanup: probe removed; leftover junit JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$NAME")"
[ -s "$L/rtl-unit.txt" ] && python3 "$H/unit-analyze.py" "$L/rtl-unit.txt" ${MODE:+--shakedown} | tee -a "$S"
say "done $(date -Is)"
