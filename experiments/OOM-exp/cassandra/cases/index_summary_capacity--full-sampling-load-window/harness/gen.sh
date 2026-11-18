#!/usr/bin/env bash
# gen.sh <set> <lo> <hi> : writes one sstable to /mydata/s4/c4-w1/data/pristine/<set>/ (log in /mydata/s4/c4-w1/logs/gen-<set>.log)
B=/mydata/s4/cassandra-base; G=/mydata/s4/c4-w1/gen; O=/mydata/s4/c4-w1/data/pristine/$1
mkdir -p $O
OPTS=$(grep -v '^#' $B/conf/jvm11-clients.options | grep -v '^$' | tr '\n' ' ')
exec taskset -c 1,3,5,7,9,11,13,15 java -Xmx8g -Xms2g $OPTS -Dcassandra.config=file://$B/conf/cassandra.yaml -Dcassandra.storagedir=/mydata/s4/c4-w1/gen/storage -Dlog4j2.disable.jmx=true -Dlogback.configurationFile=$B/conf/logback-tools.xml \
  -cp "$G:$B/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$B/build/lib/jars/*" GenSorted $O $2 $3 > /mydata/s4/c4-w1/logs/gen-$1.log 2>&1
