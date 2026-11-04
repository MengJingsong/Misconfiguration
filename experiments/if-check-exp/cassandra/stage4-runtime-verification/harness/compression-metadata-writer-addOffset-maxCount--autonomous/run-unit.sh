#!/usr/bin/env bash
# Unit tier (B2). Run on the node:  bash run-unit.sh   (tree ~/s4-cm, logs ~/s4-cm-logs)
set -u
TREE=$HOME/s4-cm; LOG=$HOME/s4-cm-logs; H=$(cd "$(dirname "$0")" && pwd)
rm -f $LOG/unit-readings.txt $LOG/c3-ea.txt $LOG/c3-da.txt
cp -f $H/ChunkOffsetGrowthTest.java $TREE/test/unit/org/apache/cassandra/io/compress/
cd $TREE
echo "== $(date -u +%FT%TZ) ant testsome ChunkOffsetGrowthTest" | tee $LOG/unit-run.log
ant testsome -Dtest.name=org.apache.cassandra.io.compress.ChunkOffsetGrowthTest </dev/null >> $LOG/unit-run.log 2>&1
echo "== ant exit $? at $(date -u +%FT%TZ)" | tee -a $LOG/unit-run.log
cp -f build/test/output/TEST-org.apache.cassandra.io.compress.ChunkOffsetGrowthTest.xml $LOG/unit-junit.xml 2>/dev/null
# C3: N=101 with assertions on and off, plain java
CP="$TREE/build/classes/main:$TREE/build/test/classes:$TREE/build/classes/thrift:$(ls $TREE/build/lib/jars/*.jar $TREE/lib/*.jar 2>/dev/null | tr '\n' ':')"
OPTS="-Dcassandra.config=file://$TREE/test/conf/cassandra.yaml -Dcassandra.storagedir=/dev/shm/s4-cm-c3 $(cat $TREE/conf/jvm11-clients.options 2>/dev/null | grep -v '^#' | tr '\n' ' ')"
for m in ea da; do
  java -$m $OPTS -Dcm.out=c3-$m.txt -cp "$CP" org.apache.cassandra.io.compress.ChunkOffsetGrowthTest > $LOG/c3-$m.stdout 2>&1; echo "c3 -$m exit $?" | tee -a $LOG/unit-run.log
done
ps -eo pid,cmd | grep '[C]hunkOffsetGrowth' | head
