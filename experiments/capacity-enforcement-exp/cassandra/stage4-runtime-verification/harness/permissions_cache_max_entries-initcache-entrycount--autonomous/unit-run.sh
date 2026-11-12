#!/usr/bin/env bash
# Unit tier (B2) of permissions_cache_max_entries-initcache-entrycount--autonomous.
# usage: bash unit-run.sh <run-name> [shakedown]
# Tree: /mydata/jingsong-cass-s4/o03/src (copy-source.sh copy, ant build-test). Output: /mydata/jingsong-cass-s4/o03/<run>/unit/.
# Copies the probe test (B2e.1, verbatim) into the tree, runs one `ant testsome -Dtest.methods=<arm>` per arm (one JVM each, B2e.2),
# collects the junit XML and the PROBE lines (B2e.3), removes the probe, runs unit-analyze.py.
# "shakedown" runs a renamed copy with N = 300 for arms m100 and m100000 only (instrument check, not a reading).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); B=/mydata/jingsong-cass-s4/o03; C=$B/src; RUN=${1:?run name}; MODE=${2:-}
CLS=PermissionsCacheMaxEntriesProbeTest; PKG=org.apache.cassandra.auth; D=test/unit/org/apache/cassandra/auth
L=$B/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C" || exit 1
say "unit-run $(date -u +%FT%TZ) host $(hostname -s) tree $(git describe --tags) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum $CLS.java unit-run.sh unit-analyze.py collect-probe.py | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
if [ "$MODE" = shakedown ]; then
  NAME=ShakedownProbeTest; ARMS="m100 m100000"
  sed -e "s/class $CLS/class $NAME/" -e 's/N = 30000/N = 300/' "$H/$CLS.java" > "$D/$NAME.java"
else
  NAME=$CLS; ARMS="m0 m100 m1000 m10000 m100000 negative shrinkAtRuntime"; cp "$H/$CLS.java" "$D/$NAME.java"
fi
rm -f build/test/output/TEST-$PKG.$NAME-*.xml build/test/logs/*/TEST-$PKG.$NAME.log*
for m in $ARMS; do
  t0=$(date +%s)
  say "arm $m start $(date -u +%FT%TZ)"
  ant testsome -Dtest.name=$PKG.$NAME -Dtest.methods=$m > "$L/ant-$m.log" 2>&1 < /dev/null
  rc=$?
  say "arm $m ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant-$m.log") $(( $(date +%s) - t0 )) s"
  cp build/test/output/TEST-$PKG.$NAME-$m.xml "$L/" 2>/dev/null || say "arm $m: NO junit XML"
done
cp build/test/logs/*/TEST-$PKG.$NAME.log* "$L/" 2>/dev/null || say "NO test log"
python3 "$H/collect-probe.py" "$L"/TEST-$PKG.$NAME.log* > "$L/probe-lines.txt"   # defect D1: stdout is in the logback log, fragmented
say "PROBE lines: $(wc -l < "$L/probe-lines.txt")"
rm -f "${D:?}/${NAME:?}.java"; rm -rf build/test/cassandra
find build/test/classes -name "$NAME*.class" -delete 2>/dev/null
say "cleanup: probe source and classes removed; leftover test JVMs: $(ps -eo args | grep -c "[j]unit.*$NAME")"
python3 "$H/unit-analyze.py" "$L/probe-lines.txt" ${MODE:+--shakedown} | tee -a "$S"
say "done $(date -u +%FT%TZ)"
