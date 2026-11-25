#!/usr/bin/env bash
# U16 stage 2 build (design §2.3): base copy from /mydata/s4/cassandra-base; iv tree = copy of the base copy + iv.patch, ant jar.
set -euo pipefail
W=/mydata/s4/u16; cd $W
[ -e cassandra-base ] || cp -a /mydata/s4/cassandra-base cassandra-base
[ -e cassandra-iv ] && { echo "cassandra-iv exists" >&2; exit 1; }
cp -a cassandra-base cassandra-iv
cd cassandra-iv
patch -p1 < $W/harness/iv.patch
rm -f build/classes/main/org/apache/cassandra/exceptions/QueryCancelledException.class
ant jar
J=build/apache-cassandra-5.0.9-SNAPSHOT.jar
echo "iv toCQLString count:   $(javap -c -classpath $J org.apache.cassandra.exceptions.QueryCancelledException | grep -c toCQLString || true)"
echo "base toCQLString count: $(javap -c -classpath $W/cassandra-base/$J org.apache.cassandra.exceptions.QueryCancelledException | grep -c toCQLString || true)"
sha256sum $J $W/cassandra-base/$J
cd $W; diff -ru cassandra-base/src cassandra-iv/src || true
