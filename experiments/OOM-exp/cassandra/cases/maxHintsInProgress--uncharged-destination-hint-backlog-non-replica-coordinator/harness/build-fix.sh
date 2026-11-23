#!/bin/bash
# B23 stage 2: build the intervention (I) tree per design §2.8. Log: /mydata/s4/b23/build-fix.log
set -x
B=/mydata/s4/b23; F=$B/cassandra-fix
rm -rf "$F"; cp -a /mydata/s4/cassandra-base "$F"
cd "$F" && patch -p1 < "$B/harness/hintsInProgress-LoadingCache.diff" || exit 1
rm -f build/classes/main/org/apache/cassandra/service/StorageProxy*.class
ant jar -Drat.skip=true || ant jar
ls -la build/*.jar
unzip -p build/apache-cassandra-5.0.9-SNAPSHOT.jar org/apache/cassandra/service/StorageProxy.class | strings | grep -c LoadingCache
echo BUILD-DONE
