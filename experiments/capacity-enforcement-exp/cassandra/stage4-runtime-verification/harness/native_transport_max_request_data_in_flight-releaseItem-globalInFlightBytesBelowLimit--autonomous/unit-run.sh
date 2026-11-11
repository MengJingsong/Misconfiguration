#!/usr/bin/env bash
# Unit tier, B2e: copy the harness test into the clone, run it with ant testsome, collect the U, lines.
# usage: bash unit-run.sh   (logs to ~/stage4-logs/pv5/unit/)
set -uo pipefail
CL=$HOME/cassandra-pv5; TOOLS=$HOME/stage4-harness-run/pv5; OUT=$HOME/stage4-logs/pv5/unit
mkdir -p "$OUT"
exec > >(tee -a "$OUT/unit-run.log") 2>&1
log() { echo "[$(date +%s%3N)] $*"; }
log "START unit tier"
git -C "$CL" describe --tags; git -C "$CL" rev-parse HEAD
sha256sum "$TOOLS/PreV5InflightCapTest.java"
cp "$TOOLS/PreV5InflightCapTest.java" "$CL/test/unit/org/apache/cassandra/transport/" || exit 1
cmp "$TOOLS/PreV5InflightCapTest.java" "$CL/test/unit/org/apache/cassandra/transport/PreV5InflightCapTest.java" && log "test file in place"
cd "$CL" || exit 1
log "+ ant testsome -Dtest.name=org.apache.cassandra.transport.PreV5InflightCapTest"
ant testsome -Dtest.name=org.apache.cassandra.transport.PreV5InflightCapTest </dev/null > "$OUT/ant-testsome.log" 2>&1
log "ant exit $?"
X=build/test/output/TEST-org.apache.cassandra.transport.PreV5InflightCapTest.xml
cp "$X" "$OUT/" 2>/dev/null
grep -E 'Tests run|BUILD|testcase' "$OUT/ant-testsome.log" | head -20
grep -o '<testsuite [^>]*>' "$X" | head -1
log "U lines (console log):"
grep -o 'U,[A-E],.*' "$OUT/ant-testsome.log" | sed 's/\s*$//' | tee "$OUT/U-lines.txt"
log "U lines (xml):"
grep -o 'U,[A-E],.*' "$X" | sed 's/\s*$//' > "$OUT/U-lines-xml.txt"; cat "$OUT/U-lines-xml.txt"
log "END unit tier"
