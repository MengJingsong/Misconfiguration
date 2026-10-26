#!/bin/bash
# Unit tier driver (B2) of cache-keys-to-save-writer-keysToSave--autonomous. Usage: bash unit-run.sh <tree> <outdir> [N]
# Copies the test into the tree (never the shared repo tree), runs it with ant testsome, then analyze_unit.py.
set -u
TREE=${1:?}; OUT=${2:?}; N=${3:-1000}
HARN=$(cd "$(dirname "$0")" && pwd)
PKG=test/unit/org/apache/cassandra/cache
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) N=$N host=$(hostname -s)"
cp "$HARN"/KeysToSaveWriterTest.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw STAGE4_N=$N; rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.cache.KeysToSaveWriterTest (STAGE4_OUT=$STAGE4_OUT N=$N)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.cache.KeysToSaveWriterTest -Dtest.timeout=3600000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
grep -q '^done=1' "$STAGE4_OUT/unit.txt" 2>/dev/null || { log "first-trigger/finish check failed: unit.txt has no done=1"; }
python3 -I "$HARN/analyze_unit.py" "$STAGE4_OUT/unit.txt" | tee "$OUT/summary.txt" | tee -a "$LOG"
log "leftover java for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
