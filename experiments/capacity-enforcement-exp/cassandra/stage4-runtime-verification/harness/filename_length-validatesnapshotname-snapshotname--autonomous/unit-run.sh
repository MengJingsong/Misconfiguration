#!/usr/bin/env bash
# Unit tier (B2) of filename_length-validatesnapshotname-snapshotname--autonomous. usage (on pc41): unit-run.sh [run-name]
# Copies SnapshotNameLengthTest into the copy ~/s4-b2/base (copy-source.sh + ant build-test), runs it with ant testsome,
# writes ~/s4-b2/logs/<stem>/<run>/unit/{test.out,summary.txt}. --remove deletes the copied test.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/s4-b2/base}; RUN=${1:-run1}
T=$C/test/unit/org/apache/cassandra/db/SnapshotNameLengthTest.java
if [ "$RUN" = "--remove" ]; then rm -f "$T" $C/build/test/classes/org/apache/cassandra/db/SnapshotNameLengthTest*.class; echo removed; exit 0; fi
L=$HOME/s4-b2/logs/filename_length-validatesnapshotname-snapshotname--autonomous/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum SnapshotNameLengthTest.java | cut -c1-12)"
cp "$H/SnapshotNameLengthTest.java" "$T"
rm -f "$L/test.out"; rm -rf build/test/cassandra
ant testsome -Dtest.name=org.apache.cassandra.db.SnapshotNameLengthTest -Dtest.jvm.args="-Dstage4.out=$L/test.out -Xmx1g" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
grep '^STAGE4 info\|^STAGE4 summary' "$L/test.out" | tee -a "$S"
say "cases: $(grep -c '^STAGE4 case' "$L/test.out") checks: $(grep -c '^STAGE4 check' "$L/test.out") ok: $(grep -c '^STAGE4 check.* ok$' "$L/test.out") MISMATCH: $(grep -c '^STAGE4 check.* MISMATCH$' "$L/test.out")"
grep '^STAGE4 check.* MISMATCH$' "$L/test.out" | tee -a "$S"
say "done $(date -Is)"
