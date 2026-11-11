#!/usr/bin/env bash
# Unit tier (B2) of default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous. usage: bash unit-run.sh <run-name> <constant> [shakedown]
# Edits SelectStatement.DEFAULT_PAGE_SIZE (line 114) in the working tree $CASSANDRA_HOME (default ~/cassandra-run1, made by copy-source.sh,
# ant build-test done) to <constant>, copies the probe in, runs ant testsome (recompiles SelectStatement only: the constant is used nowhere else),
# collects build/test/dps-unit.txt, restores the file from the git baseline, removes the probe. Output: ~/s4-dps-logs/<run>/unit-<constant>/.
# "shakedown" runs a renamed copy with 2,000 rows (instrument check, not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; RUN=${1:?run}; K=${2:?constant}; MODE=${3:-}
CLS=DefaultPageSizeProbeTest
L=$HOME/s4-dps-logs/$RUN/unit-$K; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
SS=src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
git checkout -- $SS
sed -i "s/public static final int DEFAULT_PAGE_SIZE = 10000;/public static final int DEFAULT_PAGE_SIZE = $K;/" $SS
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "constant line: $(grep -n 'int DEFAULT_PAGE_SIZE' $SS)"
say "git diff stat: $(git diff --stat | tail -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/db/filter
OUT=build/test/dps-unit.txt
if [ "$MODE" = shakedown ]; then
  NAME=${CLS/Test/ShakedownTest}
  sed -e "s/class $CLS/class $NAME/" -e 's/GROUP_ROWS = 200_000;/GROUP_ROWS = 4_000;/' -e 's#i / 20_000#i / 400#; s#i % 20_000#i % 400#' "$H/$CLS.java" > "$D/$NAME.java"
else
  NAME=$CLS; cp "$H/$CLS.java" "$D/$NAME.java"
fi
rm -f "${OUT:?}" ; rm -rf build/test/cassandra
t0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.db.filter.$NAME > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp "$OUT" "$L/dps-unit.txt" 2>/dev/null || say "NO output produced"
cp build/test/output/TEST-org.apache.cassandra.db.filter.$NAME*.xml "$L/" 2>/dev/null || true
say "DPS lines: $(grep -c '^DPS' "$L/dps-unit.txt" 2>/dev/null)"
rm -f "${D:?}/${NAME:?}.java" "${OUT:?}"; rm -rf build/test/cassandra
git checkout -- $SS
say "cleanup: probe removed, SelectStatement restored; leftover test JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$NAME")"
say "done $(date -Is)"
