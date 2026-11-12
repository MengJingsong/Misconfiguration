#!/usr/bin/env bash
# Unit tier (B2) of streaming_state_size-streammanager-states--autonomous.  usage: bash unit-run.sh [run-name] [shakedown]
# Tree: /mydata/jingsong-cass-s4/o53/src (copy-source.sh + ant build-test). Output: /mydata/jingsong-cass-s4/o53/<run>/unit/.
# Copies the test into the tree, runs ant testsome, keeps the test log and junit XML, removes the test, runs unit-analyze.py.
# "shakedown": a renamed copy with N = 500 (instrument check, not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=/mydata/jingsong-cass-s4/o53/src; RUN=${1:-run1}; MODE=${2:-}
CLS=StreamingStateCapTest; PKG=org.apache.cassandra.streaming
L=/mydata/jingsong-cass-s4/o53/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
say "unit-run $(date -u +%FT%TZ) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
D=test/unit/org/apache/cassandra/streaming
if [ "$MODE" = shakedown ]; then
  NAME=${CLS/Test/ShakedownTest}
  sed -e "s/class $CLS/class $NAME/" -e 's/N = 5000;/N = 500;/' "$H/$CLS.java" > "$D/$NAME.java"
else
  NAME=$CLS; cp "$H/$CLS.java" "$D/$NAME.java"
fi
rm -rf build/test/cassandra build/test/logs/_jdk11/TEST-$PKG.$NAME.log
t0=$(date +%s)
ant testsome -Dtest.name=$PKG.$NAME > "$L/ant.log" 2>&1 < /dev/null
rc=$?
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log") $(( $(date +%s) - t0 )) s"
cp build/test/logs/_jdk11/TEST-$PKG.$NAME.log "$L/test.log" 2>/dev/null || say "NO test log"
cp build/test/output/TEST-$PKG.$NAME*.xml "$L/" 2>/dev/null || true
grep -h 'O53' "$L/test.log" > "$L/o53-lines.txt" 2>/dev/null
say "O53 lines: $(wc -l < "$L/o53-lines.txt")"
rm -f "${D:?}/${NAME:?}.java"; rm -rf build/test/cassandra build/test/classes/org/apache/cassandra/streaming/$NAME*.class
say "cleanup: test removed; leftover test JVMs: $(ps -eo pid,args | grep -c "[j]ava.*$NAME")"
[ -s "$L/o53-lines.txt" ] && python3 "$H/unit-analyze.py" "$L/o53-lines.txt" ${MODE:+--shakedown} | tee -a "$S"
say "done $(date -u +%FT%TZ)"
