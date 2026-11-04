#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [N]
# tree: a copy-source.sh tree never used by a node. N (optional) is for the instrument check only; the run uses the default 100000.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; NN=${4:-}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) N=${NN:-default}"
cp "$HARN"/CapProbeTest.java $TREE/test/unit/org/apache/cassandra/index/sasi/disk/ || exit 1
( cd $HARN && md5sum *.java *.py *.sh *.md ) > "$OUT/harness.md5" 2>/dev/null; cat "$OUT/harness.md5" >> "$LOG"
ulimit -n 100000
export STAGE4_OUT=$OUT/raw STAGE4_TMP=${STAGE4_TMP:-$HOME/s4-pm-data/unit-tmp}
[ -n "$NN" ] && export STAGE4_N=$NN
mkdir -p "$STAGE4_OUT" "$STAGE4_TMP"
log "df: $(df -h $STAGE4_TMP | tail -1)"
log "+ ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.CapProbeTest"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.index.sasi.disk.CapProbeTest -Dtest.timeout=3000000 < /dev/null ) > "$OUT/ant.log" 2>&1
rc=$?; log "ant exit $rc"; tail -n 8 "$OUT/ant.log" | tee -a "$LOG"
rm -rf "$STAGE4_TMP"
exit $rc
