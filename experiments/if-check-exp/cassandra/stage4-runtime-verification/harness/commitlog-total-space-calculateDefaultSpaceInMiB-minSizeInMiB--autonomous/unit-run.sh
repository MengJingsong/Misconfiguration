#!/bin/bash
# Unit tier (B2, amendments 2026-10-26). Usage: bash unit-run.sh <tree> <outdir> <tmpfs4g-dir>
# Runs the existing DatabaseDescriptorTest#testCalculateDefaultSpaceInMiB, then CommitlogDefaultSpaceTest in arms H E V C D
# (one JVM each, own yaml). EXPECTED lines are checked at the end; exit 1 on any mismatch. Nothing it starts survives it.
set -u
TREE=${1:?}; OUT=${2:?}; VOL=${3:?}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p $OUT; : > $OUT/cltest.out
log() { echo "[$(date +%FT%T.%3N%z)] $*" | tee -a $OUT/session.log; }
fail() { log "FAIL: $*"; exit 1; }
[ "$(git -C $TREE describe --tags)" = cassandra-5.0.9 ] || fail "tree not at cassandra-5.0.9"
cp $HERE/CommitlogDefaultSpaceTest.java $TREE/test/unit/org/apache/cassandra/config/ || fail copy
# instrument check: test class compiles (ant testsome builds it); the known-answer checks inside it assert both WARN present and absent
df -B1M --output=size $VOL | tail -1 | tr -d ' ' > $OUT/df_vol_MiB.txt
df -B1M --output=size $TREE | tail -1 | tr -d ' ' > $OUT/df_host_MiB.txt
log "df total MiB: tmpfs=$(cat $OUT/df_vol_MiB.txt) host=$(cat $OUT/df_host_MiB.txt)"
[ "$(cat $OUT/df_vol_MiB.txt)" = 4096 ] || fail "tmpfs is not 4096 MiB"
HOSTD=$OUT/hostdirs; mkdir -p $HOSTD/cl $HOSTD/cdc $VOL/cl $VOL/cdc
log "+ ant testsome DatabaseDescriptorTest#testCalculateDefaultSpaceInMiB"
( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.config.DatabaseDescriptorTest -Dtest.methods=testCalculateDefaultSpaceInMiB </dev/null ) > $OUT/ant-existing.log 2>&1
grep -E 'Tests run|BUILD' $OUT/ant-existing.log | tee -a $OUT/session.log
for arm in H E V C D; do
  Y=$OUT/arm-$arm.yaml
  case $arm in
    H|E) CL=$HOSTD/cl; CDC=$HOSTD/cdc;;
    V)   CL=$VOL/cl;   CDC=$HOSTD/cdc;;
    C)   CL=$VOL/cl;   CDC=$VOL/cdc;;
    D)   CL=$HOSTD/cl; CDC=$HOSTD/cdc;;
  esac
  sed -e "s#^commitlog_directory:.*#commitlog_directory: $CL#" -e "s#^cdc_raw_directory:.*#cdc_raw_directory: $CDC#" $TREE/test/conf/cassandra.yaml > $Y
  [ $arm = C ] || [ $arm = D ] && sed -i 's#^cdc_enabled:.*#cdc_enabled: true#' $Y
  [ $arm = E ] && echo "commitlog_total_space: 64MiB" >> $Y
  grep -c '^commitlog_total_space' $Y | sed "s/^/arm $arm commitlog_total_space lines: /" | tee -a $OUT/session.log
  diff $TREE/test/conf/cassandra.yaml $Y > $OUT/arm-$arm.yaml.diff
  log "+ ant testsome CommitlogDefaultSpaceTest arm $arm (cl=$CL cdc=$CDC)"
  ( cd $TREE && ant testsome -Dtest.name=org.apache.cassandra.config.CommitlogDefaultSpaceTest -Dtest.methods=run \
      "-Dtest.jvm.args=-Dcassandra.config=file://$Y -Dcltest.arm=$arm -Dcltest.cldir=$CL -Dcltest.cdcdir=$CDC -Dcltest.out=$OUT/cltest.out" </dev/null ) > $OUT/ant-$arm.log 2>&1
  grep -E 'Tests run|BUILD' $OUT/ant-$arm.log | tee -a $OUT/session.log
  cp $TREE/build/test/logs/TEST-org.apache.cassandra.config.CommitlogDefaultSpaceTest-run.xml $OUT/TEST-$arm.xml 2>/dev/null
  grep -h 'Small \(commitlog\|cdc\) volume detected' $TREE/build/test/logs/*CommitlogDefaultSpaceTest* 2>/dev/null | grep -v '/path' | head -3 > $OUT/warn-$arm.txt
done
# EXPECTED lines: check the RESULT file
P=$(grep -c '^RESULT PASS' $OUT/cltest.out); F=$(grep -c '^RESULT FAIL' $OUT/cltest.out); D=$(grep -c '^RESULT DONE failures=0' $OUT/cltest.out)
log "RESULT lines: PASS=$P FAIL=$F DONE(failures=0)=$D"
exp() { grep -q "$1" $OUT/cltest.out && log "EXPECTED ok: $1" || { log "EXPECTED MISSING: $1"; RC=1; }; }
RC=0
exp 'PASS rep1 CL 32768MiB expected=8192 actual=8192'
exp 'PASS rep1 CL 32767MiB expected=8191 actual=8191'
exp 'PASS rep1 CL 0 expected=0 actual=0'
exp 'PASS rep1 CL 1TiB expected=8192 actual=8192'
exp 'PASS rep1 CDC 1TiB expected=4096 actual=4096'
exp 'PASS E explicit commitlog_total_space expected=64 actual=64'
exp 'PASS V derived commitlog_total_space = min(8192, total/4) expected=1024 actual=1024'
exp 'PASS C derived cdc_total_space = min(4096, total/8) expected=512 actual=512'
exp 'PASS D derived cdc_total_space = min(4096, total/8) expected=4096 actual=4096'
exp 'PASS H derived commitlog_total_space = min(8192, total/4) expected=8192 actual=8192'
[ $F = 0 ] && [ $D = 5 ] || RC=1
log "unit-run end rc=$RC"
exit $RC
