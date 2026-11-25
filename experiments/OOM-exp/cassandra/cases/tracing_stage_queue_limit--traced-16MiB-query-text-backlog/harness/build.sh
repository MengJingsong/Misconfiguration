#!/usr/bin/env bash
# B28 stage-2 build on the node (2026-11-24): copy the node's built base tree twice (base = cassandra, intervention =
# cassandra-iv), apply iv.patch to the iv copy's src, delete the TraceStateImpl classes, `ant jar`, check with javap.
# Never runs ant in /mydata/s4/cassandra-base. Log: $W/build.log
W=/mydata/s4/b28; B=/mydata/s4/cassandra-base; JAR=build/apache-cassandra-5.0.9-SNAPSHOT.jar
exec >> $W/build.log 2>&1
for t in cassandra cassandra-iv; do echo "$(date +%FT%T%z) copy $t"; [ -e $W/$t ] && { echo "$W/$t exists"; exit 1; }; cp -a $B $W/$t; done
cd $W/cassandra-iv
cp src/java/org/apache/cassandra/tracing/TraceStateImpl.java $W/TraceStateImpl.java.orig
git apply --recount $W/harness/iv.patch && echo "patch applied" || { echo "PATCH FAILED"; exit 1; }
diff -u $W/TraceStateImpl.java.orig src/java/org/apache/cassandra/tracing/TraceStateImpl.java > $W/harness/iv.diff.applied
rm -f build/classes/main/org/apache/cassandra/tracing/TraceStateImpl*.class
echo "$(date +%FT%T%z) ant jar (iv)"
ant jar > $W/build-iv-ant.log 2>&1; rc=$?
echo "$(date +%FT%T%z) ant rc=$rc"; tail -3 $W/build-iv-ant.log
echo "B28_QUEUED_BYTES in base: $(javap -p -c -classpath $W/cassandra/$JAR org.apache.cassandra.tracing.TraceStateImpl | grep -c B28_QUEUED_BYTES)"
echo "B28_QUEUED_BYTES in iv:   $(javap -p -c -classpath $JAR org.apache.cassandra.tracing.TraceStateImpl | grep -c B28_QUEUED_BYTES)"
md5sum $W/cassandra/$JAR $JAR $W/cassandra/conf/cassandra.yaml $JAR conf/cassandra.yaml
echo "$(date +%FT%T%z) BUILD-DONE"
