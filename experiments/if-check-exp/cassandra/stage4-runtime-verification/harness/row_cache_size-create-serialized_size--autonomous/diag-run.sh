#!/bin/bash
# POST-HOC diagnostic driver. Usage: bash diag-run.sh <tree> <harness-dir> <outdir>
set -u
TREE=${1:?}; HARN=${2:?}; OUT=${3:?}; mkdir -p $OUT/classes
CP="$TREE/build/classes/main:$(ls $TREE/lib/*.jar | tr '\n' ':')$(ls $TREE/build/lib/jars/*.jar | tr '\n' ':')"
javac -cp "$CP" -d $OUT/classes $HARN/SerializingCacheDiag.java || exit 1
OPTS=$(grep -v '^#' $TREE/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
ulimit -n 100000; : > $OUT/diag.txt
for S in 4096 262144; do
  for T in 1 16; do
    for AM in default 1; do
      if [ $AM = 1 ]; then export MALLOC_ARENA_MAX=1; else unset MALLOC_ARENA_MAX; fi
      echo "[$(date +%T)] diag S=$S T=$T arena=$AM"
      java -Xmx512m -Xms512m -XX:+AlwaysPreTouch $OPTS -cp "$OUT/classes:$CP" SerializingCacheDiag $OUT/diag.txt 64 $S $T 20 > $OUT/stdout-$S-$T-$AM.log 2>&1 || echo FAILED
    done
  done
done
echo done
