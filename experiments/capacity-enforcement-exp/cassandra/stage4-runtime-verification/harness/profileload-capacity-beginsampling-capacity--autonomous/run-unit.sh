#!/bin/bash
# Unit tier (B2e) for o123, run on ms0604. Logs every command.
set -u
WORK=/mydata/jingsong-cass-s4/o123
H=$WORK/harness
OUT=$WORK/run1/unit-restart
mkdir -p $OUT
exec > >(tee -a $OUT/run-unit.log) 2>&1
run() { echo "+ [$(date -u +%FT%TZ)] $*"; "$@"; rc=$?; echo "  rc=$rc"; return $rc; }
cd $WORK/cassandra-5.0.9 || exit 1
run java -version; run ant -version; run uname -m
run bash -c 'ant jar build-test </dev/null > '$OUT'/build.log 2>&1'; tail -3 $OUT/build.log
grep -q 'BUILD SUCCESSFUL' $OUT/build.log || { echo "BUILD FAILED"; exit 1; }
run cp $H/MaxSamplerCapacityProbeTest.java test/unit/org/apache/cassandra/metrics/
run md5sum test/unit/org/apache/cassandra/metrics/MaxSamplerCapacityProbeTest.java
run bash -c 'ant testsome -Dtest.name=org.apache.cassandra.metrics.MaxSamplerCapacityProbeTest </dev/null > '$OUT'/testsome.log 2>&1'
tail -5 $OUT/testsome.log
X=build/test/output/TEST-org.apache.cassandra.metrics.MaxSamplerCapacityProbeTest.xml
run cp $X $OUT/
LOGF=build/test/logs/_jdk11/TEST-org.apache.cassandra.metrics.MaxSamplerCapacityProbeTest.log; run cp $LOGF $OUT/; grep -o 'RESULT.*' $LOGF | tee $OUT/result-lines.txt
run grep -o '<testsuite[^>]*>' $X
run grep -c '<failure\|<error' $X
echo "+ pgrep check"; ps -eo pid,cmd | grep '[M]axSamplerCapacityProbeTest' || echo "no MaxSamplerCapacityProbeTest process"
echo DONE
