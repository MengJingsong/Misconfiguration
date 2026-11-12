#!/usr/bin/env bash
# Wrapper for run-4 B6Load (rate cap optional). Compiled into /mydata/b6/loadcls4 by:
#   javac -cp "$CP" -d /mydata/b6/loadcls4 B6Load.java
J=/mydata/b6/cassandra/build/lib/jars
CP="/mydata/b6/loadcls4:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
exec java -Xmx4g -cp "$CP" -Dlogback.configurationFile=$H/../harness-run2/logback-load.xml B6Load "$@"
