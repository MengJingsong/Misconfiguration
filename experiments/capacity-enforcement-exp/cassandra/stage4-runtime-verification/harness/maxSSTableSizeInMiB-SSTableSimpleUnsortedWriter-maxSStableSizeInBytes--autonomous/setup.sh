#!/usr/bin/env bash
# o116 setup on the node (S4-A1(a)): fresh work dir, cp -a of the built base, add the probe test, build-test, compile BulkProbe.
set -x
W=/mydata/jingsong-cass-s4/o116
date -u +%FT%TZ; hostname; uname -m; nproc; free -g; df -h /mydata; java -version 2>&1; ant -version
[ -d /mydata/jingsong-cass-s4 ] || { sudo mkdir -p /mydata/jingsong-cass-s4 && sudo chown $(id -un):$(id -gn) /mydata/jingsong-cass-s4; }
rm -rf $W; mkdir -p $W/logs $W/run/u $W/run/p $W/harness
cp -a /mydata/s4/cassandra-base $W/src
# S4-A4(a): the caller scp's the harness to /mydata/jingsong-cass-s4/o116-harness.new (own folder, no /tmp); moved in here
mv $W/../o116-harness.new/* $W/harness/ && rmdir $W/../o116-harness.new
cd $W/src && md5sum src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java src/java/org/apache/cassandra/cql3/statements/DeleteStatement.java build.xml conf/jvm11-clients.options
cp $W/harness/MaxSSTableSizeProbeTest.java $W/src/test/unit/org/apache/cassandra/io/sstable/
ant -q build-test </dev/null > $W/logs/build-test.log 2>&1; echo "build-test exit=$?"; tail -3 $W/logs/build-test.log
ls -l $W/src/build/test/classes/org/apache/cassandra/io/sstable/MaxSSTableSizeProbeTest.class
CP="$W/src/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$W/src/build/lib/jars/*"
cp $W/harness/BulkProbe.java $W/run/p/ && cd $W/run/p && javac -cp "$CP" BulkProbe.java; echo "javac exit=$?"; ls -l $W/run/p
date -u +%FT%TZ; echo SETUP-DONE
