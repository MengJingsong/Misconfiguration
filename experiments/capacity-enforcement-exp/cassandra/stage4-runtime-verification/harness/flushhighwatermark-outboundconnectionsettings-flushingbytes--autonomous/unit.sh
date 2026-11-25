#!/bin/bash
# o125 unit tier (B2e, with S4-A1). Runs ON the node. Logs every command and its output.
set -uo pipefail
WORK=/mydata/jingsong-cass-s4/o125
H=$WORK/harness
LOG=$WORK/logs
mkdir -p $LOG
exec > >(tee -a $LOG/unit-driver.log) 2>&1
set -x
date -u; hostname; uname -m; java -version; ant -version; df -h /mydata
cd $WORK || exit 1
if [ ! -d $WORK/src ]; then cp -a /mydata/s4/cassandra-base $WORK/src || exit 1; fi
cp $H/FlushWaterMarkTest.java $WORK/src/test/unit/org/apache/cassandra/net/FlushWaterMarkTest.java || exit 1
cd $WORK/src || exit 1
# B2e step 2 + 4: three runs, keep every row
for r in 1 2 3; do
  date -u
  ant -Dno-checkstyle=true testsome -Dtest.name=org.apache.cassandra.net.FlushWaterMarkTest </dev/null > $LOG/unit-r$r.log 2>&1
  echo "ant exit r$r: $?"
  cp build/test/output/TEST-org.apache.cassandra.net.FlushWaterMarkTest.xml $LOG/unit-r$r.xml 2>/dev/null
  cp build/test/logs/*/TEST-org.apache.cassandra.net.FlushWaterMarkTest.log $LOG/ 2>/dev/null
  grep -E 'BUILD|Tests run' $LOG/unit-r$r.log
  # defect fix #1: rows are split over log lines; rejoin them
  python3 $H/extract-rows.py $LOG/unit-r$r.log | tee $LOG/unit-r$r.rows
done
# B2e step 5
ps -eo pid,cmd | grep '[F]lushWaterMarkTest' || echo "no FlushWaterMarkTest process left"
date -u
