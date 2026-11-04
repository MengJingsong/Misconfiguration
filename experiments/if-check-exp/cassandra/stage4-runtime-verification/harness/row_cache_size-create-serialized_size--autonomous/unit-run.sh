#!/bin/bash
# Unit tier driver. Usage: bash unit-run.sh <tree> <harness-dir> <outdir> [scale]
# Compiles SerializingCacheCapTest against <tree>/build/classes/main and runs it with a fixed 512 MiB pre-touched heap.
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; SCALE=${4:-1}
mkdir -p "$OUT"; LOG=$OUT/session.log
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a "$LOG"; }
log "unit-run start tree=$TREE head=$(git -C $TREE rev-parse --short HEAD) scale=$SCALE"
( cd $HARN && md5sum *.java *.py *.sh ) | tee -a "$LOG" > "$OUT/harness.md5"
CP="$TREE/build/classes/main:$(ls $TREE/lib/*.jar | tr '\n' ':')$(ls $TREE/build/lib/jars/*.jar | tr '\n' ':')"
mkdir -p $OUT/classes
log "+ javac"; javac -cp "$CP" -d $OUT/classes $HARN/SerializingCacheCapTest.java 2>&1 | tee -a "$LOG" ; [ ${PIPESTATUS[0]} -eq 0 ] || exit 1
OPTS=$(grep -v '^#' $TREE/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
OPTS=$(grep -v '^#' $TREE/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
ulimit -n 100000
rm -f $OUT/obs.txt; : > $OUT/stdout.log
runj() { log "+ java -Xmx512m -Xms512m -XX:+AlwaysPreTouch <clients.options> SerializingCacheCapTest $*"; java -Xmx512m -Xms512m -XX:+AlwaysPreTouch $OPTS -cp "$OUT/classes:$CP" SerializingCacheCapTest $OUT/obs.txt $SCALE "$@" >> $OUT/stdout.log 2>&1 || { log "FAILED rc=$?: $*"; exit 1; }; }
for rep in 1 2 3; do runj control $rep; done
for rep in 1 2 3; do for C in 16 64 256; do for S in 4096 262144 4194304; do runj point $C $S $rep; done; done; done
for rep in 1 2 3; do runj clear $rep; done
log "done; obs lines: $(wc -l < $OUT/obs.txt)"
log "leftover java for this class: [$(ps -eo pid,args | grep "[S]erializingCacheCapTest" | awk '{print $1}' | tr '\n' ' ')]"
