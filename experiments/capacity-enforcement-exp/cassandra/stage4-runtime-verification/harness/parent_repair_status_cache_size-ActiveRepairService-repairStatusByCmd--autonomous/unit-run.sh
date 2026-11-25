#!/usr/bin/env bash
# Unit tier (B2e) of case o127. On the node: bash unit-run.sh <outdir> <label> "<test.jvm.args>"
set -uo pipefail
TREE=/mydata/jingsong-cass-s4/o127/c509; OUT=$1; LABEL=$2; JARGS=$3
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
LOG=$OUT/run-$LABEL.log
exec > >(tee -a "$LOG") 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
T=org.apache.cassandra.service.ParentRepairStatusCapTest
DST=$TREE/test/unit/org/apache/cassandra/service/ParentRepairStatusCapTest.java
log "label=$LABEL host=$(hostname) arch=$(uname -m) tree=$TREE"
cp "$HERE/ParentRepairStatusCapTest.java" "$DST"; log "md5 $(md5sum "$DST")"
cd "$TREE"
rm -f build/test/output/TEST-$T.xml; find build/test/logs -name "*ParentRepairStatusCapTest*" -delete 2>/dev/null
log "ant testsome -Dtest.name=$T -Dtest.jvm.args=\"$JARGS\""
ant testsome -Dtest.name=$T "-Dtest.jvm.args=$JARGS" </dev/null
log "ant exit=$?"
cp build/test/output/TEST-$T.xml "$OUT/TEST-$LABEL.xml" 2>/dev/null || log "no xml"
TL=$(find build/test/logs -name "*ParentRepairStatusCapTest*" | head -1); [ -n "$TL" ] && cp "$TL" "$OUT/testlog-$LABEL.log" && log "test log $TL"
grep -ho 'O127 [^<"]*' "$OUT/TEST-$LABEL.xml" "$OUT/testlog-$LABEL.log" 2>/dev/null | sed "s/^/READING $LABEL /"   # S4-A2: the lines go to the test log (logger), not the XML
grep -o 'tests="[0-9]*"\|failures="[0-9]*"\|errors="[0-9]*"' "$OUT/TEST-$LABEL.xml" 2>/dev/null | head -3 | tr '\n' ' '; echo
grep -o '<error[^>]*>' "$OUT/TEST-$LABEL.xml" 2>/dev/null | head -3
pgrep -f ParentRepairStatusCapTest >/dev/null && log "LEFTOVER test JVM" || log "no test JVM left"
