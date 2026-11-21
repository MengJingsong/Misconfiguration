#!/usr/bin/env bash
# R15: patch Parser.g in the ivb copy (harness/ivb.patch), regenerate the grammar (ant gen-cql3-grammar via ant jar), rebuild.
W=/mydata/s4/r15-w5; JAR=build/apache-cassandra-5.0.9-SNAPSHOT.jar
exec >> $W/build-ivb.log 2>&1
cd $W/cassandra-ivb
cp src/antlr/Parser.g /tmp/r15-Parser.g.orig
git apply $W/harness/ivb.patch && echo "patch applied" || { echo "PATCH FAILED"; exit 1; }
diff -u /tmp/r15-Parser.g.orig src/antlr/Parser.g > $W/harness/ivb.diff.applied
rm -f build/classes/main/org/apache/cassandra/cql3/Cql*.class
echo "$(date +%FT%T%z) ant jar (ivb)"
ant jar > $W/build-ivb-ant.log 2>&1; rc=$?
echo "$(date +%FT%T%z) ant rc=$rc"
grep -n "Building Grammar" $W/build-ivb-ant.log
ls -l --time-style=+%FT%T src/gen-java/org/apache/cassandra/cql3/Cql_Parser.java src/gen-java/org/apache/cassandra/cql3/Cql.tokens
echo "checkMarkerCount in Cql_Parser: $(javap -p -classpath $JAR org.apache.cassandra.cql3.Cql_Parser | grep -c checkMarkerCount)"
echo "checkMarkerCount in base: $(javap -p -classpath $W/cassandra/$JAR org.apache.cassandra.cql3.Cql_Parser | grep -c checkMarkerCount)"
md5sum $W/cassandra/$JAR $JAR
echo "$(date +%FT%T%z) BUILD-DONE ivb"
