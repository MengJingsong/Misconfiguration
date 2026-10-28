#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir>
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}
PKG=test/unit/org/apache/cassandra/cache
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) changed=[$(git -C $TREE status --short | grep -v NopCacheCapTest | tr '\n' ' ')]"
cp "$HARN"/NopCacheCapTest.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh *.yaml 2>/dev/null ) > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw; rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.cache.NopCacheCapTest (STAGE4_OUT=$STAGE4_OUT)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.cache.NopCacheCapTest -Dtest.timeout=3600000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 12 "$OUT/ant.log" | tee -a "$LOG"
cp "$STAGE4_OUT/unit.txt" "$OUT/unit.txt" 2>/dev/null
log "leftover java for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
