#!/usr/bin/env bash
# Compile U1Load / U1Sample against the jars of the read-only 5.0.9 build (/mydata/b6/cassandra).
J=/mydata/b6/cassandra/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p /mydata/u1/cls && javac -cp "$CP" -d /mydata/u1/cls "$H/U1Load.java" "$H/U1Sample.java" && echo built
