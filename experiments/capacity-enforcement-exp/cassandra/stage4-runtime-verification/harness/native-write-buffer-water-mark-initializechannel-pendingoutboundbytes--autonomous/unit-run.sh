#!/bin/bash
# usage: unit-run.sh <outdir> <label> "<-Dwm.* args>"   (runs one B2e cell; logs every command)
set -u
T=/mydata/jingsong-cass-s4/o133/c509; OUT=$1; L=$2; ARGS=$3
mkdir -p $OUT; LOG=$OUT/run-$L.log
cd $T || exit 1
{ echo "### $(date -u +%FT%T.%3NZ) label=$L args=[$ARGS]"
  echo "+ ant testsome -Dtest.name=org.apache.cassandra.transport.WriteWaterMarkBacklogTest -Dtest.jvm.args=\"$ARGS\""
} >> $LOG
rm -f build/test/output/TEST-org.apache.cassandra.transport.WriteWaterMarkBacklogTest.xml
ant testsome -Dtest.name=org.apache.cassandra.transport.WriteWaterMarkBacklogTest -Dtest.jvm.args="$ARGS" </dev/null >> $LOG 2>&1
rc=$?
echo "### $(date -u +%FT%T.%3NZ) ant rc=$rc" >> $LOG
cp build/test/output/TEST-org.apache.cassandra.transport.WriteWaterMarkBacklogTest.xml $OUT/TEST-$L.xml 2>/dev/null
grep -h -o 'WMRESULT.*' $LOG 2>/dev/null | sort -u | sed "s/^/$L /" >> $OUT/wmresult.txt
grep -h -o '<testsuite[^>]*>' $OUT/TEST-$L.xml 2>/dev/null | head -1 >> $LOG
cp build/test/logs/_jdk11/TEST-org.apache.cassandra.transport.WriteWaterMarkBacklogTest.log $OUT/testlog-$L.log 2>/dev/null
rm -rf build/test/cassandra
exit $rc
