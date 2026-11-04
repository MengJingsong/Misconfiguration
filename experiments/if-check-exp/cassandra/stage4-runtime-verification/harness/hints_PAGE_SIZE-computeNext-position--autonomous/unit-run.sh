#!/usr/bin/env bash
# Unit tier (B2, as amended 2026-10-26) of hints_PAGE_SIZE-computeNext-position--autonomous.
# usage: source ~/Library/Caches/stage4/env.sh; unit-run.sh [extra jvm args]
#   run 1:     unit-run.sh                                   (v in {1 KiB, 16 KiB, 600 KiB} x {plain, lz4}, both iterators)
#   shakedown: L=$W/logs/<stem>/shakedown-unit unit-run.sh "-Dhpcap.sizes=16384"
# Env: C (clone, default $W/cassandra-run37), L (log dir). Default test JVM options otherwise (B2a).
set -uo pipefail
S=hints_PAGE_SIZE-computeNext-position--autonomous
H=$(cd "$(dirname "$0")" && pwd); C=${C:-$W/cassandra-run37}
L=${L:-$W/logs/$S/unit}
JA="${1:-}"
mkdir -p "$L"; rm -f "$L"/*
log() { echo "[$(date '+%F %T')] $*" | tee -a "$L/commands.log"; }
log "unit-run clone=$C $(git -C "$C" describe --tags) $(git -C "$C" rev-parse HEAD) status_entries=$(git -C "$C" status --short | wc -l | tr -d ' ') jvm-args=[$JA]"
pgrep -f 'cassandra.service.Cassandra''Daemon' >/dev/null && { log "ABORT: a Cassandra daemon is running"; exit 1; }
CLS=org.apache.cassandra.hints.HintsPageCapTest
T=$C/test/unit/org/apache/cassandra/hints/HintsPageCapTest.java
cp "$H/HintsPageCapTest.java" "$T"; log "test copied to $T (sha256 $(shasum -a 256 "$T" | cut -c1-16))"
rm -rf "$C/build/test/logs" "$C/build/test/output/TEST-$CLS.xml"
if [ -n "$JA" ]; then
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS -Dtest.jvm.args=\"$JA\""
  ( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS -Dtest.jvm.args="$JA" ) > "$L/ant.log" 2>&1
else
  log "+ ant -Dlocal.repository=\$W/m2 testsome -Dtest.name=$CLS"
  ( cd "$C" && ant -Dlocal.repository="$W/m2" testsome -Dtest.name=$CLS ) > "$L/ant.log" 2>&1
fi
rc=$?
tl=$(find "$C/build/test/logs" -name "TEST-$CLS.log" 2>/dev/null | head -1)
[ -n "$tl" ] && cp "$tl" "$L/TEST.log"
cp "$C/build/test/output/TEST-$CLS.xml" "$L/TEST.xml" 2>/dev/null
grep -o 'HPCAP.*' "$L/TEST.log" 2>/dev/null > "$L/hpcap.txt"
log "ant rc=$rc; $(grep -m1 -E 'Tests run' "$L/ant.log" || echo 'no Tests run line'); HPCAP lines=$(wc -l < "$L/hpcap.txt" | tr -d ' ')"
{ echo "ant rc=$rc"; grep -E 'Tests run|BUILD' "$L/ant.log"; grep -E '^HPCAP-(SETUP|FILE|END)' "$L/hpcap.txt"; } > "$L/summary.txt"
rm -f "$T"
rm -rf "$C/build/test/classes/org/apache/cassandra/hints/HintsPageCapTest"*.class
log "test removed; git status: $(git -C "$C" status --short | wc -l | tr -d ' ') entries"
python3 -I "$H/summarize.py" unit "$L" > "$L/readings.txt" 2>> "$L/commands.log"; log "readings.txt written ($(wc -l < "$L/readings.txt" | tr -d ' ') lines)"
log "unit-run done"
