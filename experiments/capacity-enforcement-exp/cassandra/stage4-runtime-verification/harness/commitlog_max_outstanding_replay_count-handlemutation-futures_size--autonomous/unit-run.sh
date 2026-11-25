#!/usr/bin/env bash
# Unit tier (B2) of case o100. Usage on the node: bash unit-run.sh <tree> <outdir> <label> "<test.jvm.args>"
set -uo pipefail
TREE=$1; OUT=$2; LABEL=$3; JARGS=$4
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
LOG=$OUT/run-$LABEL.log
exec > >(tee -a "$LOG") 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
T=org.apache.cassandra.db.commitlog.ReplayOutstandingCountTest
DST=$TREE/test/unit/org/apache/cassandra/db/commitlog/ReplayOutstandingCountTest.java
log "label=$LABEL host=$(hostname) arch=$(uname -m) tree=$TREE"
cp "$HERE/ReplayOutstandingCountTest.java" "$DST"; log "md5 $(md5sum "$DST")"
cd "$TREE"
rm -f build/test/output/TEST-$T.xml; find build/test/logs -name "*ReplayOutstandingCountTest*" -delete 2>/dev/null
log "ant testsome -Dtest.name=$T -Dtest.jvm.args=\"$JARGS\""
ant testsome -Dtest.name=$T "-Dtest.jvm.args=$JARGS" </dev/null
log "ant exit=$?"
cp build/test/output/TEST-$T.xml "$OUT/TEST-$LABEL.xml" 2>/dev/null || log "no xml"
TL=$(find build/test/logs -name "*ReplayOutstandingCountTest*" | head -1); [ -n "$TL" ] && cp "$TL" "$OUT/testlog-$LABEL.log" && log "test log $TL"
R=$(grep -ho 'RESULT count_cap=[^<"]*' "$OUT/TEST-$LABEL.xml" "$OUT/testlog-$LABEL.log" 2>/dev/null | head -1)
log "READING $LABEL $R"
grep -o 'tests="[0-9]*"\|failures="[0-9]*"\|errors="[0-9]*"' "$OUT/TEST-$LABEL.xml" 2>/dev/null | head -3 | tr '\n' ' '; echo
pgrep -f ReplayOutstandingCountTest >/dev/null && log "LEFTOVER test JVM" || log "no test JVM left"
