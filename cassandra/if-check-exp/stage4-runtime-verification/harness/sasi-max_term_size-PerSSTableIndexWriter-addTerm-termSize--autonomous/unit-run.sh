#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [scale]
# tree: a copy-source.sh tree never used by a node. scale (optional) divides every N: instrument check only.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; SC=${4:-}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date -u +%FT%T.%3NZ)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) scale=${SC:-1}"
cp "$HARN"/WriterProbeTest.java $TREE/test/unit/org/apache/cassandra/index/sasi/disk/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh ) > "$OUT/harness.md5" 2>/dev/null; cat "$OUT/harness.md5" >> "$LOG"
ulimit -n 100000
export STAGE4_OUT=$OUT/raw STAGE4_TMP=${STAGE4_TMP:-$HOME/s4-pw-data/unit-tmp}
[ -n "$SC" ] && export STAGE4_SCALE=$SC
mkdir -p "$STAGE4_OUT" "$STAGE4_TMP"
log "df: $(df -h $STAGE4_TMP | tail -1)"
log "+ ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.WriterProbeTest"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.WriterProbeTest -Dtest.timeout=3000000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?; log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
rm -rf "$STAGE4_TMP"
exit $rc
