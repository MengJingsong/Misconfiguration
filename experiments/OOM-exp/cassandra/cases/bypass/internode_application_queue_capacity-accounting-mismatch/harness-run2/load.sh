#!/usr/bin/env bash
# Wrapper for B6Load (compiled into /mydata/b6/loadcls by: javac -cp "$CP" -d /mydata/b6/loadcls B6Load.java)
J=/mydata/b6/cassandra/build/lib/jars
CP="/mydata/b6/loadcls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
exec java -Xmx4g -cp "$CP" -Dlogback.configurationFile=$H/logback-load.xml B6Load "$@"
