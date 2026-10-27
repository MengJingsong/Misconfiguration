#!/usr/bin/env bash
# Unit tier, B2e: copy the harness test into the working tree, run it with ant testsome, collect the U, lines.
# usage: bash unit-run.sh [LABEL]   (logs to ~/s4-b8-pi-logs/unit-LABEL/; default LABEL=run1)
set -uo pipefail
LABEL=${1:-run1}
CL=$HOME/s4-b8-pi; TOOLS=$HOME/s4-b8-pi-harness; OUT=$HOME/s4-b8-pi-logs/unit-$LABEL
mkdir -p "$OUT"
exec > >(tee -a "$OUT/unit-run.log") 2>&1
log() { echo "[$(date +%s%3N)] $*"; }
log "START unit tier $LABEL"
git -C "$CL" describe --tags; git -C "$CL" rev-parse HEAD
sha256sum "$TOOLS/PerIpInFlightLimitTest.java"
cp "$TOOLS/PerIpInFlightLimitTest.java" "$CL/test/unit/org/apache/cassandra/transport/" || exit 1
cmp "$TOOLS/PerIpInFlightLimitTest.java" "$CL/test/unit/org/apache/cassandra/transport/PerIpInFlightLimitTest.java" && log "test file in place"
# slot 4: move the test node's internode ports off the defaults other cases use (working tree only)
sed -i 's/^listen_address: .*/listen_address: 127.0.4.1/; s/^storage_port: .*/storage_port: 7042/; s/^ssl_storage_port: .*/ssl_storage_port: 17042/; s/- seeds: .*/- seeds: "127.0.4.1:7042"/' "$CL/test/conf/cassandra.yaml"
grep -nE '^(listen_address|storage_port|ssl_storage_port)' "$CL/test/conf/cassandra.yaml"
cd "$CL" || exit 1
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.transport.PerIpInFlightLimitTest"
ant testsome -Dtest.name=org.apache.cassandra.transport.PerIpInFlightLimitTest </dev/null > "$OUT/ant-testsome.log" 2>&1
log "ant exit $?"
X=build/test/output/TEST-org.apache.cassandra.transport.PerIpInFlightLimitTest.xml
cp "$X" "$OUT/" 2>/dev/null
grep -E 'Tests run|BUILD|testcase' "$OUT/ant-testsome.log" | head -20
grep -o '<testsuite [^>]*>' "$X" | head -1
log "U lines (console log):"
grep -o 'U,[A-Z][a-z]*,.*' "$OUT/ant-testsome.log" | sed 's/\s*$//' | tee "$OUT/U-lines.txt"
log "END unit tier"
