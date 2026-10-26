#!/usr/bin/env bash
# Unit tier (B2). Run on the node:  bash run-unit.sh   (tree ~/s4-cs, logs ~/s4-cs-logs)
set -u
TREE=$HOME/s4-cs; LOG=$HOME/s4-cs-logs
rm -f $LOG/unit-readings.txt
cd $TREE
echo "== $(date -u +%FT%TZ) ant testsome ChunkBufferGrowthTest" | tee $LOG/unit-run.log
ant testsome -Dtest.name=ChunkBufferGrowthTest </dev/null >> $LOG/unit-run.log 2>&1
echo "== ant exit $? at $(date -u +%FT%TZ)" | tee -a $LOG/unit-run.log
ls build/test/output 2>/dev/null | head
cp -f build/test/output/TEST-org.apache.cassandra.io.compress.ChunkBufferGrowthTest.xml $LOG/unit-junit.xml 2>/dev/null
ps -eo pid,cmd | grep '[C]hunkBufferGrowth' | head
