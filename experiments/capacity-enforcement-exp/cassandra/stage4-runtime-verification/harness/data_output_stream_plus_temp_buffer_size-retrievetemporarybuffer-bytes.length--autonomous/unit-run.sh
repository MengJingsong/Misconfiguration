#!/bin/bash
# B2e as filed (amendment A1 paths). Usage: bash unit-run.sh  -> logs under $WORK/run1/unit/
set -euo pipefail
WORK=/mydata/jingsong-cass-s4/o43
HARNESS=$(cd "$(dirname "$0")" && pwd)
OUT=$WORK/run1/unit; mkdir -p $OUT $WORK/probe/org/apache/cassandra/io/util $WORK/probe-out
exec > >(tee -a $OUT/unit-session.log) 2>&1
set -x
cp $HARNESS/TempBufferProbe.java $WORK/probe/org/apache/cassandra/io/util/
cd $WORK/src
CP="build/classes/main:build/lib/jars/*:lib/*"
javac -cp "$CP" -d $WORK/probe-out $WORK/probe/org/apache/cassandra/io/util/TempBufferProbe.java
OPENS=$(grep -E '^--add-(exports|opens)' conf/jvm11-server.options | tr '\n' ' ')
for P in 4096 default 1048576 16777216; do
  D=""; [ "$P" != default ] && D="-Dcassandra.data_output_stream_plus_temp_buffer_size=$P"
  java -Xms1g -Xmx1g $OPENS $D -cp "$WORK/probe-out:$CP" org.apache.cassandra.io.util.TempBufferProbe \
     | tee $OUT/unit-$P.log
done
pgrep -f TempBufferProbe || echo "no TempBufferProbe left"
