#!/usr/bin/env bash
# R18 gen.sh <set> <lo> <hi> : one sstable to /mydata/s4/r18/data/pristine/<set>/ (log /mydata/s4/r18/logs/gen-<set>.log).
# R10's gen.sh with the root changed to /mydata/s4/r18 (design §2.5 phase 1); same GenSorted, same shipped yaml (read only).
B=/mydata/s4/cassandra-base; G=/mydata/s4/r18/gen; O=/mydata/s4/r18/data/pristine/$1
mkdir -p $O
OPTS=$(grep -v '^#' $B/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
exec taskset -c 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31 java -Xmx8g -Xms2g $OPTS -Dcassandra.config=file://$B/conf/cassandra.yaml -Dcassandra.storagedir=/mydata/s4/r18/gen/storage-$1 -Dlog4j2.disable.jmx=true -Dlogback.configurationFile=$B/conf/logback-tools.xml \
  -cp "$G:$B/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$B/build/lib/jars/*" GenSorted $O $2 $3 > /mydata/s4/r18/logs/gen-$1.log 2>&1
