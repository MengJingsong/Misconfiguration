#!/usr/bin/env bash
# Unit tier (B2) of trie-pathreconstructor-keybytes-growth--autonomous (frozen sha256 in the results file section 1).
# usage on the run node: bash unit-run.sh [run-name]     output: ~/s4-tp33-logs/<run-name>/unit/
#  copies the test into the tree (~/s4-tp33), ant testsome, collects build/test/tp33-unit.txt + junit XML, removes the test, analyzes.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-tp33}; RUN=${1:-run1}
CLS=PathReconstructorSizeTest; L=$HOME/s4-tp33-logs/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
say "df: $(df -h ~ | tail -1)"
D=test/unit/org/apache/cassandra/db/tries
cp "$H/$CLS.java" "$D/$CLS.java"
rm -rf build/test/cassandra build/test/tp33-unit.txt
rm -f build/test/output/TEST-org.apache.cassandra.db.tries.$CLS*.xml
t0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.db.tries.$CLS > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp build/test/tp33-unit.txt "$L/tp33-unit.txt" 2>/dev/null || say "NO output produced"
cp build/test/output/TEST-org.apache.cassandra.db.tries.$CLS*.xml "$L/" 2>/dev/null || true
say "TP33 lines: $(grep -c '^TP33' "$L/tp33-unit.txt" 2>/dev/null)"
rm -f "$D/$CLS.java" build/test/tp33-unit.txt
rm -rf build/test/cassandra
say "cleanup: test removed; leftover junit JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$CLS")"
[ -s "$L/tp33-unit.txt" ] && python3 -I "$H/unit-analyze.py" "$L/tp33-unit.txt" | tee -a "$S"
say "done $(date -Is)"
