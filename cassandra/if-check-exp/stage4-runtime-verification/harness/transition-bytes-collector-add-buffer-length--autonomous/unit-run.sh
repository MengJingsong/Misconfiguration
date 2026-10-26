#!/usr/bin/env bash
# Unit tier (B2) of transition-bytes-collector-add-buffer-length--autonomous (frozen sha256 in the results file section 1).
# usage on the run node: bash unit-run.sh [run-name]     output: ~/s4-b7-tc-logs/<run-name>/unit/
#  1. copies the test into the tree (~/s4-b7-tc), `ant testsome` (forked JVM, 1 GiB) -> tc-unit.txt and tc-env.txt (class path, JVM args)
#  2. runs the same class under org.junit.runner.JUnitCore with -Xmx256m, -Xmx512m (tc-unit-x256m.txt, tc-unit-x512m.txt)
#  3. removes the test and runs unit-analyze.py
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b7-tc}; RUN=${1:-run1}
CLS=CollectorGrowthTest; PK=org.apache.cassandra.io.tries; L=$HOME/s4-b7-tc-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/io/tries
cp "$H/$CLS.java" "$D/$CLS.java"
rm -rf build/test/cassandra build/test/tc-unit*.txt build/test/tc-env.txt
rm -f build/test/output/TEST-$PK.$CLS*.xml
t0=$(date +%s)
ant testsome -Dtest.name=$PK.$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp build/test/tc-unit.txt "$L/tc-unit.txt" 2>/dev/null || say "NO output produced"
cp build/test/tc-env.txt "$L/" 2>/dev/null
cp build/test/output/TEST-$PK.$CLS*.xml "$L/" 2>/dev/null || true
if [ -s "$L/tc-env.txt" ]; then
  CP=$(grep '^CP=' "$L/tc-env.txt" | head -1 | cut -c4-)
  mapfile -t ARGS < <(grep '^ARG=' "$L/tc-env.txt" | cut -c5- | grep -v -e '^-Xmx' -e '^-Xms' -e '^-Xss')
  for X in 256m 512m; do
    t1=$(date +%s)
    ( cd "$C" && java -Xmx$X "${ARGS[@]}" -Dtc.tag=x$X -Dtc.out=$L/tc-unit-x$X.txt -cp "$CP" org.junit.runner.JUnitCore $PK.$CLS > "$L/junit-x$X.log" 2>&1 < /dev/null )
    say "junitcore -Xmx$X exit=$? $(grep -m1 -E '^OK|^Tests run' "$L/junit-x$X.log") $(( $(date +%s) - t1 )) s"
  done
fi
say "TC lines: $(cat "$L"/tc-unit*.txt 2>/dev/null | grep -c '^TC')"
rm -f "$D/$CLS.java"
rm -rf build/test/cassandra build/test/tc-unit*.txt build/test/tc-env.txt
say "cleanup: test removed; leftover junit JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$CLS")"
[ -s "$L/tc-unit.txt" ] && python3 -I "$H/unit-analyze.py" "$L" | tee -a "$S"
say "done $(date -Is)"
