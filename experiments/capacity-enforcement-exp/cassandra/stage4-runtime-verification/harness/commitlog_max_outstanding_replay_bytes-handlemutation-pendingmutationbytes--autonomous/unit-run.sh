#!/usr/bin/env bash
# Unit tier (B2) of case commitlog_max_outstanding_replay_bytes-...--autonomous (o32).
# Usage (on the stage-4 node): bash unit-run.sh <tree> <outdir> [shakedown]
#   run:       the four frozen limits (test default 1 MiB, 4 MiB, 16 MiB, 1 GiB)
#   shakedown: known-answer check with L = 1 byte (expect peakPending = s of the current entry, maxQueued = 1)
set -euo pipefail
TREE=$1; OUT=$2; MODE=${3:-run}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
exec > >(tee -a "$OUT/unit-session.txt") 2>&1
log() { echo "+ $(date -u +%FT%TZ) [$(date +%s%3N)] $*"; }
CLS=org.apache.cassandra.db.commitlog.OutstandingReplayBytesProbeTest
DST=$TREE/test/unit/org/apache/cassandra/db/commitlog/OutstandingReplayBytesProbeTest.java
log "mode=$MODE tree=$TREE out=$OUT host=$(hostname)"
log "md5 $(md5sum "$HERE/OutstandingReplayBytesProbeTest.java")"
cp "$HERE/OutstandingReplayBytesProbeTest.java" "$DST"
if [ "$MODE" = shakedown ]; then export O32_LIMITS=1; fi
log "O32_LIMITS=${O32_LIMITS:-<default>} O32_SLEEP_MS=${O32_SLEEP_MS:-<default 5>}"
cd "$TREE"
rm -f build/test/output/TEST-$CLS.xml build/test/output/TEST-$CLS.txt
log "ant testsome -Dtest.name=$CLS"
set +e
ant testsome -Dtest.name=$CLS </dev/null
RC=$?
set -e
log "ant exit=$RC"
cp build/test/output/TEST-$CLS.xml "$OUT/" 2>/dev/null || log "no xml"
cp build/test/output/TEST-$CLS.txt "$OUT/" 2>/dev/null || true
grep -ho 'O32 [A-Z]*=.*' "$OUT/unit-session.txt" | grep -v 'O32_' > "$OUT/unit-o32.txt" || true
log "readings:"; cat "$OUT/unit-o32.txt"
grep -o 'tests="[0-9]*" ' "$OUT/TEST-$CLS.xml" | head -1; grep -o 'failures="[0-9]*"\|errors="[0-9]*"' "$OUT/TEST-$CLS.xml" | head -2
log "done"
exit $RC
