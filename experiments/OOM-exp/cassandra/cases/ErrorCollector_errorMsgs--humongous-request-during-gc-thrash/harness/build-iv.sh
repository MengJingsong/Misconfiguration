#!/usr/bin/env bash
# R15 (from U6's build-iv.sh): copy the shared base tree (base, iv, ivb), then patch and rebuild iv and ivb, one after
# the other (never ant in a tree a node runs from). Logs: $W/build-iv.log, $W/build-ivb.log.
W=/mydata/s4/r15-w5; B=/mydata/s4/cassandra-base; JAR=build/apache-cassandra-5.0.9-SNAPSHOT.jar
exec >> $W/build-iv.log 2>&1
for t in cassandra cassandra-iv cassandra-ivb; do echo "$(date +%FT%T%z) copy $t"; cp -a $B $W/$t; done
cd $W/cassandra-iv
cp src/java/org/apache/cassandra/cql3/ErrorCollector.java /tmp/r15-ErrorCollector.java.orig
git apply $W/harness/iv.patch && echo "patch applied" || { echo "PATCH FAILED"; exit 1; }
diff -u /tmp/r15-ErrorCollector.java.orig src/java/org/apache/cassandra/cql3/ErrorCollector.java > $W/harness/iv.diff.applied
base_n=$(javap -p -c -classpath $W/cassandra/$JAR org.apache.cassandra.cql3.ErrorCollector | grep -c isEmpty)
rm -f build/classes/main/org/apache/cassandra/cql3/ErrorCollector*.class
echo "$(date +%FT%T%z) ant jar (iv)"
ant jar > $W/build-iv-ant.log 2>&1; rc=$?
echo "$(date +%FT%T%z) ant rc=$rc"
iv_n=$(javap -p -c -classpath $JAR org.apache.cassandra.cql3.ErrorCollector | grep -c isEmpty)
echo "isEmpty count base=$base_n iv=$iv_n"
md5sum $W/cassandra/$JAR $JAR
echo "$(date +%FT%T%z) BUILD-DONE iv"
bash $W/harness/build-ivb.sh
