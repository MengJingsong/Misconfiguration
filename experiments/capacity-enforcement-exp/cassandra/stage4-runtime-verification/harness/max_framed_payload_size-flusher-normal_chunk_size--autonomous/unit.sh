#!/usr/bin/env bash
# o132 unit tier (case file B2e): one fresh JVM per cell and repetition.
set -uo pipefail
W=${W:-/mydata/jingsong-cass-s4/o132}
LOG=$W/logs/unit.log
mkdir -p $W/logs/unit
exec > >(tee -a "$LOG") 2>&1
cd $W/src
CLASSPATH=$(cat $W/classpath.txt)
CJ="$(grep -hv '^\s*#' $W/src/conf/jvm-clients.options $W/src/conf/jvm11-clients.options | grep -v '^\s*$' | tr '\n' ' ') -XX:MaxDirectMemorySize=2g -Dio.netty.tryReflectionSetAccessible=true"
echo "=== unit.sh start $(date) CJ=$CJ"
OUT=$W/unit.csv
one() { # K N codec cache rep
  local K=$1 N=$2 codec=$3 cache=$4 rep=$5
  local tag="K=${K:-unset},N=$N,codec=$codec,cache=$cache,rep=$rep"
  local f=$W/logs/unit/$(echo "$tag" | tr ',=' '_-').log
  echo "+ [$(date +%s%3N)] $tag"
  echo "CELL,$tag" >> $OUT
  java $CJ -cp "$W/probe/classes:$CLASSPATH" ${K:+-Dcassandra.test.max_framed_payload_size=$K} -Dprobe.cache_mib=$cache \
       org.apache.cassandra.transport.FlusherProbe $N $codec > $f 2>&1
  local rc=$?
  grep -E 'RESULT|AFTER' $f | tee -a $OUT
  [ $rc -eq 0 ] || { echo "RC=$rc for $tag"; echo "ERROR,rc=$rc" >> $OUT; tail -20 $f; }
}
# 1. Main matrix: K x N, crc, cache 512 MiB, 3 reps.
for K in "" 65536 16384 4096; do
  for N in 1048576 4194304 16777216; do
    for rep in 1 2 3; do one "$K" $N crc 512 $rep; done
  done
done
# 2. Positive control: K unset, N = 16 MiB, crc, cache 4 MiB.
for rep in 1 2 3; do one "" 16777216 crc 4 $rep; done
# 3. LZ4 cells: K unset and 16384, N = 4 MiB.
for K in "" 16384; do for rep in 1 2 3; do one "$K" 4194304 lz4 512 $rep; done; done
echo "=== unit.sh done $(date)"
