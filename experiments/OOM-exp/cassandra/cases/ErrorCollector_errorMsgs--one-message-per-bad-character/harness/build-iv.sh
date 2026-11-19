#!/usr/bin/env bash
# U6: copy the shared base tree twice (base, iv); patch and rebuild the iv copy. Log: $W/build-iv.log
W=/mydata/s4/u6-w4; B=/mydata/s4/cassandra-base
exec >> $W/build-iv.log 2>&1
echo "$(date +%FT%T%z) copy base"
cp -a $B $W/cassandra
echo "$(date +%FT%T%z) copy iv"
cp -a $B $W/cassandra-iv
cd $W/cassandra-iv
git apply $W/harness/iv.patch && echo "patch applied" || { echo "PATCH FAILED"; exit 1; }
git diff > $W/harness/iv.diff.applied
base_n=$(javap -p -c -classpath $W/cassandra/build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.cql3.ErrorCollector | grep -c isEmpty)
rm -f build/classes/main/org/apache/cassandra/cql3/ErrorCollector*.class
echo "$(date +%FT%T%z) ant jar"
ant jar > $W/build-iv-ant.log 2>&1; rc=$?
echo "$(date +%FT%T%z) ant rc=$rc"
iv_n=$(javap -p -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.cql3.ErrorCollector | grep -c isEmpty)
echo "isEmpty count base=$base_n iv=$iv_n"
md5sum $W/cassandra/build/apache-cassandra-5.0.9-SNAPSHOT.jar build/apache-cassandra-5.0.9-SNAPSHOT.jar
echo "$(date +%FT%T%z) BUILD-DONE"
