#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh
#   shakedown: L=$W/logs/<stem>/shakedown-unit unit-run.sh "-Dtest.methods=t3"   (extra ant args in $1)
# Env: C (clone, default $W/cassandra-run38), L (log dir). Default test JVM options; heap is 1 GiB (amendment B2a:
# testsome's junit task sets maxmemory=1024m, build.xml:1153, appended after test.jvm.args so -Dtest.jvm.args=-Xmx4G does not
# override it -- checked in shakedown-unit2; the case's 4G comes from build.xml:1245-1255, which testsome does not use).
set -uo pipefail
S=indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run38}
L=${L:-$W/logs/$S/unit}
XA="${1:-}"
mkdir -p "$L"; rm -f "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') extra=[$XA]"
pgrep -f 'cassandra.service.Cassandra''Daemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
CLS=org.apache.cassandra.index.IndexingPageSizeProbeTest
T=$C/test/unit/org/apache/cassandra/index/IndexingPageSizeProbeTest.java
cp "$H/IndexingPageSizeProbeTest.java" "$T"; log "test copied to $T (sha256 $(shasum -a 256 "$T" | cut -c1-16))"
rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS"*.xml
log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS $XA"
( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS $XA ) > "$L/ant.log" 2>&1
rc=$?
tl=$(find "$C/build/test/logs" -name "TEST-$CLS*.log" 2>/dev/null | head -1)
[ -n "$tl" ] && cp "$tl" "$L/TEST.log"
cp "$C/build/test/output/TEST-$CLS"*.xml "$L/TEST.xml" 2>/dev/null
grep -o 'ITP .*' "$L/TEST.log" 2>/dev/null > "$L/itp.txt"
log "ant rc=$rc; $(grep -m1 -E 'Tests run' "$L/ant.log" || echo 'no Tests run line'); ITP lines=$(wc -l < "$L/itp.txt" | tr -d ' ')"
{ echo "ant rc=$rc"; grep -E 'Tests run|BUILD|Testcase' "$L/ant.log"; cat "$L/itp.txt" | sed -E 's/ rowsPerPage=.*//'; } > "$L/summary.txt"
rm -f "$T"
rm -rf "$C/build/test/classes/org/apache/cassandra/index/IndexingPageSizeProbeTest"*.class
log "test removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
log "unit-run done"
