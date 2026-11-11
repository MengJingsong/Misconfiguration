#!/usr/bin/env bash
# usage: run-cell.sh <tree> <outdir> <mode> <threshold-MiB> <compressor> <B-bytes> <nHints> <R>
# one JVM per cell; writes <outdir>/<cell>.log; last line "OBS done" expected.
set -u
TREE=$1; OUT=$2; MODE=$3; TH=$4; COMP=$5; B=$6; N=$7; R=$8
CELL=${MODE}_t${TH}_${COMP%Compressor}_B${B}_R${R}
WD=$OUT/work/$CELL; mkdir -p $WD $OUT/cells
Y=$WD/cassandra.yaml
sed -e "s#build/test/cassandra#$WD#g" -e 's/^file_cache_enabled:.*/file_cache_enabled: false/' $TREE/test/conf/cassandra.yaml > $Y
echo "file_cache_size: ${TH}MiB" >> $Y
CP="$TREE/build/classes/main:$TREE/build/test/classes:$(ls $TREE/build/lib/jars/*.jar $TREE/build/test/lib/jars/*.jar $TREE/lib/*.jar 2>/dev/null | tr '\n' ':')$OUT/classes"
cd $TREE
ulimit -n 100000
timeout 300 java -Xmx1g -XX:MaxDirectMemorySize=3g -Dcassandra.config=file://$Y -Dcassandra.skip_sync=true -Dcassandra.ring_delay_ms=1000 \
  -Dlogback.configurationFile=$TREE/test/conf/logback-test.xml -Dcassandra.storagedir=$WD/storage \
  --add-exports java.base/jdk.internal.misc=ALL-UNNAMED --add-exports java.base/jdk.internal.ref=ALL-UNNAMED --add-exports java.base/sun.nio.ch=ALL-UNNAMED \
  --add-exports java.management.rmi/com.sun.jmx.remote.internal.rmi=ALL-UNNAMED --add-exports java.rmi/sun.rmi.registry=ALL-UNNAMED \
  --add-exports java.rmi/sun.rmi.server=ALL-UNNAMED --add-exports java.sql/java.sql=ALL-UNNAMED --add-opens java.base/java.lang.module=ALL-UNNAMED \
  --add-opens java.base/jdk.internal.loader=ALL-UNNAMED --add-opens java.base/jdk.internal.ref=ALL-UNNAMED --add-opens java.base/jdk.internal.reflect=ALL-UNNAMED \
  --add-opens java.base/jdk.internal.math=ALL-UNNAMED --add-opens java.base/jdk.internal.module=ALL-UNNAMED --add-opens java.base/jdk.internal.util.jar=ALL-UNNAMED \
  --add-opens jdk.management/com.sun.management.internal=ALL-UNNAMED --add-opens java.base/sun.nio.ch=ALL-UNNAMED --add-opens java.base/java.io=ALL-UNNAMED \
  --add-opens java.base/java.nio=ALL-UNNAMED --add-opens java.base/java.util=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED \
  -cp "$CP" org.apache.cassandra.hints.FcsReadBufferMain $MODE $COMP $B $N $R > $OUT/cells/$CELL.log 2>&1
echo "exit=$?" >> $OUT/cells/$CELL.log
rm -rf $WD
grep -c '^OBS done' $OUT/cells/$CELL.log | sed "s#^#$CELL done=#"
