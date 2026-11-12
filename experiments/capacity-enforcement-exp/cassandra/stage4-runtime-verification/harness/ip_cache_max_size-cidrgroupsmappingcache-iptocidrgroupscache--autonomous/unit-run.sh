#!/usr/bin/env bash
# Unit tier (B2e) of ip_cache_max_size--autonomous. Runs on the node, from $WORK.
# Usage: bash unit-run.sh <outdir-name> [values] [n]
#   e.g. bash unit-run.sh run1                  -> max in {0,100,100000,1000000}, n=600000
#        bash unit-run.sh shake "0 1000" 2000   -> shakedown
set -euo pipefail
WORK=/mydata/jingsong-cass-s4/o04
HDIR=$WORK/harness
OUT=$WORK/logs/${1:?outdir}/unit
VALUES=${2:-"0 100 100000 1000000"}
N=${3:-600000}
mkdir -p $OUT
exec > >(tee -a $OUT/unit-session.txt) 2>&1
log(){ echo "+ $(date -u +%FT%TZ) $*"; }
cd $WORK/src
log "harness md5"; md5sum $HDIR/IpCacheMaxSizeProbeTest.java
cp $HDIR/IpCacheMaxSizeProbeTest.java test/unit/org/apache/cassandra/auth/IpCacheMaxSizeProbeTest.java
trap 'rm -f $WORK/src/test/unit/org/apache/cassandra/auth/IpCacheMaxSizeProbeTest.java' EXIT
for M in $VALUES; do
  log "ant testsome max=$M n=$N"
  rm -f build/test/output/TEST-org.apache.cassandra.auth.IpCacheMaxSizeProbeTest*.xml
  ant testsome -Dtest.name=org.apache.cassandra.auth.IpCacheMaxSizeProbeTest \
      -Dtest.jvm.args="-Dprobe.max=$M -Dprobe.n=$N" </dev/null > $OUT/unit-$M.log 2>&1 || log "ant exit $? (see unit-$M.log)"
  cp build/test/output/TEST-org.apache.cassandra.auth.IpCacheMaxSizeProbeTest*.xml $OUT/TEST-max$M.xml || log "no junit xml"
  log "PROBE lines max=$M"
  python3 $HDIR/unit-extract.py $M $OUT/unit-$M.log | tee -a $OUT/probe-lines.txt
  grep -E 'Tests run|BUILD' $OUT/unit-$M.log || true
done
log "unit done"
