#!/bin/bash
# Stage-4 unit tier (B2e), case o122 rowsize-checkcanread-bytesread--autonomous. Runs on ms0640.
# usage: unit-run.sh check|run1
set -u
RUN=/mydata/jingsong-cass-s4/o122
H=$RUN/harness
MODE=${1:?check|run1}
OUT=$RUN/unit/$MODE
mkdir -p $OUT
exec > >(tee -a $OUT/session.log) 2>&1
log(){ echo "[$(date -u +%FT%TZ) $(date +%s%3N)] $*"; }
log "mode=$MODE host=$(hostname) arch=$(uname -m)"
cp $H/TrackedDataInputPlusLimitTest.java $RUN/src/test/unit/org/apache/cassandra/io/util/
md5sum $H/* > $OUT/harness.md5
cd $RUN/src
export S4_OUT=$OUT/results.txt
rm -f $S4_OUT
if [ "$MODE" = check ]; then
  METHODS="-Dtest.methods=instrumentKnownAnswer,testLimitFires"
else
  METHODS=""
fi
log "ant testsome $METHODS"
ant testsome -Dtest.name=org.apache.cassandra.io.util.TrackedDataInputPlusLimitTest $METHODS </dev/null > $OUT/ant.log 2>&1
rc=$?
log "ant rc=$rc"
grep -E "Tests run|BUILD" $OUT/ant.log
cp $RUN/src/build/test/output/TEST-org.apache.cassandra.io.util.TrackedDataInputPlusLimitTest*.xml $OUT/ 2>/dev/null
log "results:"; cat $S4_OUT
log "leftover JVMs:"; ps -eo pid,cmd | grep '[T]rackedDataInputPlusLimitTest' || echo none
log "done"
