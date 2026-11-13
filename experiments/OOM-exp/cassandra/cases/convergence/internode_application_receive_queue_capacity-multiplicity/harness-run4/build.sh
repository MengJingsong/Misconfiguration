#!/usr/bin/env bash
J=/mydata/b6/cassandra/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
mkdir -p /mydata/c1r4/cls && javac -cp "$CP" -d /mydata/c1r4/cls "$H/C1Load.java" "$H/C1Sample.java" && echo built
