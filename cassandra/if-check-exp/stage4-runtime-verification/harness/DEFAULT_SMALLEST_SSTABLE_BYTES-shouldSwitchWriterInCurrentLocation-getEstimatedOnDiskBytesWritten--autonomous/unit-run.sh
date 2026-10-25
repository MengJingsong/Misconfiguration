#!/bin/bash
# Unit tier driver, DEFAULT_SMALLEST_SSTABLE_BYTES case.
# Usage: bash unit-run.sh <tree> <harness-dir> <TestClassSimpleName> <outdir> [parts]
# Copies the harness Java into <tree>, runs `ant testsome` for the class, logs everything to <outdir>/session.log.
set -u
TREE=${1:?}; HARN=${2:?}; CLS=${3:?}; OUT=${4:?}; PARTS=${5:-}
PKG=test/unit/org/apache/cassandra/db/compaction/writers
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start class=$CLS tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) parts=${PARTS:-default}"
mkdir -p $TREE/$PKG
cp "$HARN"/SplitWriterHarnessBase.java "$HARN"/$CLS.java $TREE/$PKG/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
export STAGE4_OUT=$OUT/raw; [ -n "$PARTS" ] && export STAGE4_PARTS=$PARTS
rm -rf "$STAGE4_OUT"; mkdir -p "$STAGE4_OUT"
ulimit -n 100000
log "+ ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.$CLS (STAGE4_OUT=$STAGE4_OUT)"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.$CLS -Dtest.timeout=7200000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?
log "ant exit $rc"; tail -n 12 "$OUT/ant.log" | tee -a "$LOG"
log "leftover daemons/ant for this tree: [$(ps -eo pid,args | grep "[j]ava.*$TREE" | awk '{print $1}' | tr '\n' ' ')]"
exit $rc
