#!/bin/bash
# Stage-4 unit tier (B2e) for maxSSTableSizeInMiB-SSTableSimpleWriter-maxSSTableSizeInBytes--autonomous, run 1.
# Runs on pc82 (x86_64). Logs every command and its output; stops at the first failed step.
set -euo pipefail
S4=/mydata/jingsong-cass-s4/o117
SRC=$S4/cassandra-5.0.9
LOG=$S4/logs
mkdir -p $LOG
exec > >(tee -a $LOG/unit-run.log) 2>&1
set -x
date -u +%FT%TZ; hostname; uname -m; java -version 2>&1 | head -1; ant -version
export PROBE_DIR=$S4/probe-unit
export PROBE_OUT=$S4/probe-unit.csv

# B2a (S1): copy the built base
if [ ! -d $SRC ]; then cp -a /mydata/s4/cassandra-base $SRC; fi
# provenance (the base has no .git): compare with the repository source over NFS
REPO_SRC=/proj/misconfiguration-PG0/git-repos/Misconfiguration/systems/cassandra/source
diff -rq $SRC/src/java $REPO_SRC/src/java && echo SRC_JAVA_SAME
diff -rq $SRC/test/unit $REPO_SRC/test/unit && echo TEST_UNIT_SAME
grep -m1 base.version $SRC/build.xml

# B2e step 1: probe into the copy, compile
cp $S4/harness/MaxSSTableSizeProbeTest.java $SRC/test/unit/org/apache/cassandra/io/sstable/
cd $SRC
ant build-test </dev/null > $LOG/unit-build-test.log 2>&1 || { tail -50 $LOG/unit-build-test.log; echo "STEP_FAIL build-test"; exit 1; }
tail -3 $LOG/unit-build-test.log
ls -l build/test/classes/org/apache/cassandra/io/sstable/MaxSSTableSizeProbeTest.class

# B2e step 2
rm -rf $PROBE_DIR $PROBE_OUT && mkdir -p $PROBE_DIR

# B2e step 3: positive control
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.CQLSSTableWriterClientTest -Dtest.methods=testWriteWithSortedAndMaxSize -Dno-build-test=true </dev/null > $LOG/unit-poscontrol.log 2>&1 || true
grep -E 'Tests run|BUILD|testWriteWithSortedAndMaxSize' $LOG/unit-poscontrol.log | head -20
cp build/test/output/TEST-org.apache.cassandra.io.sstable.CQLSSTableWriterClientTest*.xml $LOG/ 2>/dev/null || true
grep -q 'BUILD SUCCESSFUL' $LOG/unit-poscontrol.log || { echo "STEP_FAIL positive control"; exit 1; }

# B2e step 4: probe
T0=$(date +%s)
ant testsome -Dtest.name=org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest -Dno-build-test=true </dev/null > $LOG/unit-probe.log 2>&1 || true
echo "probe wall s: $(( $(date +%s) - T0 ))"
grep -E 'Tests run|BUILD' $LOG/unit-probe.log | head -20
cp build/test/output/TEST-org.apache.cassandra.io.sstable.MaxSSTableSizeProbeTest*.xml $LOG/ 2>/dev/null || true
cp $PROBE_OUT $LOG/probe-unit.csv || true
wc -l $PROBE_OUT || true
grep -q 'BUILD SUCCESSFUL' $LOG/unit-probe.log || { echo "STEP_FAIL probe"; exit 1; }

# B2e step 6
du -sb $PROBE_DIR || true
rm -rf $PROBE_DIR
ps -eo cmd | grep -E '[j]unit|[C]assandraDaemon' | cut -c1-150 || true
date -u +%FT%TZ
echo UNIT_DONE
