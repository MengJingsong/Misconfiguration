#!/usr/bin/env bash
# Unit tier (B2) of group-by-limit-incrementGroupCount-groupLimit--autonomous. usage: bash unit-run.sh [run-name] [shakedown]
# Output: ~/s4-b11-l79-logs/<run-name>/unit/. Copies the probe into the tree ~/s4-b11-l79 (made by copy-source.sh, ant build-test),
# runs ant testsome, collects build/test/l79-unit.txt and the junit XML, removes the probe, runs unit-analyze.py.
# "shakedown" runs a renamed copy with a 20,000-row partition and 20-row groups instead of 1,000,000 and 1000 (instrument check, not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b11-l79}; RUN=${1:-run1}; MODE=${2:-}
CLS=GroupLimitProbeTest
L=$HOME/s4-b11-l79-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/db/filter
OUT=build/test/l79-unit.txt
if [ "$MODE" = shakedown ]; then
  NAME=${CLS/Test/ShakedownTest}
  sed -e "s/class $CLS/class $NAME/" -e 's/{ 1000, 100_000, 1_000_000 }/{ 1000, 5_000, 20_000 }/' -e 's/S_ROWS = 1_000_000/S_ROWS = 20_000/' -e 's/M_ROWS = 1000;/M_ROWS = 20;/' "$H/$CLS.java" > "$D/$NAME.java"
else
  NAME=$CLS; cp "$H/$CLS.java" "$D/$NAME.java"
fi
rm -f "${OUT:?}" ; rm -rf build/test/cassandra
t0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.db.filter.$NAME > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp "$OUT" "$L/l79-unit.txt" 2>/dev/null || say "NO output produced"
cp build/test/output/TEST-org.apache.cassandra.db.filter.$NAME*.xml "$L/" 2>/dev/null || true
say "L79 lines: $(grep -c '^L79' "$L/l79-unit.txt" 2>/dev/null)"
rm -f "${D:?}/${NAME:?}.java" "${OUT:?}"; rm -rf build/test/cassandra
say "cleanup: probe removed; leftover test JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$NAME")"
[ -s "$L/l79-unit.txt" ] && python3 "$H/unit-analyze.py" "$L/l79-unit.txt" ${MODE:+--shakedown} | tee -a "$S"
say "done $(date -Is)"
