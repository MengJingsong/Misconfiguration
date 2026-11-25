#!/usr/bin/env bash
# Stage-4 unit tier (B2e) for dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous, order 20.
# Runs on the node in the per-case source copy $R/src. Every command and its output goes to $R/logs/unit/unit-run.log.
set -uo pipefail
R=/mydata/jingsong-s4/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity-run1
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64 PATH=/usr/lib/jvm/java-8-openjdk-amd64/bin:$PATH YARN_IGNORE_ENGINES=true
L=$R/logs/unit; mkdir -p $L
LOG=$L/unit-run.log
run() { echo "+ [$(date -u +%FT%TZ)] $*" | tee -a $LOG; "$@" 2>&1 | tee -a $LOG; local rc=${PIPESTATUS[0]}; echo "rc=$rc" | tee -a $LOG; return $rc; }
M=hadoop-hdfs-project/hadoop-hdfs
T=$M/src/test/java/org/apache/hadoop/hdfs/qjournal/server
REP=$R/src/$M/target/surefire-reports
cd $R/src
run hostname
run java -version
run mvn -v
run md5sum $R/harness/*
run cp $R/harness/TestJournaledEditsCacheCap.java $T/
run git -C $R/src status --short
# Step 2: U1-U3 (default 2 GiB surefire heap; capu.histo enables the U1 histogram)
run mvn -B -pl $M test -Dtest='TestJournaledEditsCacheCap#testCumulativeCap+testSingleBatchBoundary+testDerivedDefault' \
  -Dmaven-surefire-plugin.argLine="-Xmx2048m -Dcapu.histo=true"
mkdir -p $L/u123; cp $REP/*TestJournaledEditsCacheCap* $L/u123/ 2>/dev/null
# Step 3: U4 alone with -Xmx5g
run mvn -B -o -pl $M surefire:test -Dtest='TestJournaledEditsCacheCap#testIntOverflowAtMaxCapacity' \
  -Dmaven-surefire-plugin.argLine="-Xmx5g -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=$R/logs/unit"
mkdir -p $L/u4; cp $REP/*TestJournaledEditsCacheCap* $L/u4/ 2>/dev/null
# Step 4: regression baseline
run mvn -B -o -pl $M surefire:test -Dtest='TestJournaledEditsCache'
mkdir -p $L/baseline; cp $REP/*TestJournaledEditsCache.txt $REP/*TestJournaledEditsCache-output.txt $L/baseline/ 2>/dev/null
grep -h '^CAPU ' $L/u123/*-output.txt $L/u4/*-output.txt > $L/capu-readings.txt 2>/dev/null
run wc -l $L/capu-readings.txt
run git -C $R/src status --short
echo "UNIT-DONE $(date -u +%FT%TZ)" | tee -a $LOG
