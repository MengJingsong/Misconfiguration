#!/usr/bin/env bash
# Unit tier of native_transport_max_concurrent_connections-channelActive-limit--guided (case 9a Procedure 1).
# usage (on the measured node): unit-run.sh [run-name]      output: ~/stage4-logs/ncc/<run-name, default run1>/unit/
# Copies ConnectionLimitHandlerTest into the clone's test tree, runs it with ant testsome, and writes the STAGE4 check
# lines and an EXPECTED summary into summary.txt. No agent: the test reads the handler's counter by reflection.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); C=${CASSANDRA_HOME:-$HOME/cassandra-run1}; RUN=${1:-run1}
L=$HOME/stage4-logs/ncc/$RUN/unit; mkdir -p "$L"; S=$L/summary.txt; : > "$S"
say() { echo "$*" | tee -a "$S"; }
cd "$C"
say "unit-run $(date -Is) host $(hostname -s) clone $(git describe --tags) $(git rev-parse --short HEAD) java $(java -version 2>&1 | head -1)"
say "harness md5 $(cd "$H" && md5sum ConnectionLimitHandlerTest.java unit-run.sh | awk '{printf "%s=%s ", $2, substr($1,1,12)}')"
cp "$H/ConnectionLimitHandlerTest.java" test/unit/org/apache/cassandra/transport/
rm -f "$L/test.out"
ant testsome -Dtest.name=org.apache.cassandra.transport.ConnectionLimitHandlerTest \
  -Dtest.jvm.args="-Dstage4.out=$L/test.out" > "$L/ant.log" 2>&1 < /dev/null
rc=$?
cp build/test/output/TEST-org.apache.cassandra.transport.ConnectionLimitHandlerTest*.xml "$L/" 2>/dev/null || true
say "ant exit=$rc $(grep -m1 -o 'Tests run: [0-9]*, Failures: [0-9]*, Errors: [0-9]*, Skipped: [0-9]*' "$L/ant.log")"
grep '^STAGE4' "$L/test.out" | tee -a "$S"
ok=$(grep -c '^STAGE4 check .* ok$' "$L/test.out"); bad=$(grep -c 'MISMATCH$' "$L/test.out")
say "EXPECTED: every STAGE4 check matches (ok=$ok, mismatch=$bad) — $([ "$bad" = 0 ] && [ "$ok" -gt 0 ] && echo yes || echo NO)"
say "EXPECTED: ant testsome passed (exit $rc) — $([ "$rc" = 0 ] && echo yes || echo NO)"
