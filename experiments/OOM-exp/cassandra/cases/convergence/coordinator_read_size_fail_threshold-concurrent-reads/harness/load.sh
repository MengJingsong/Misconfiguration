#!/usr/bin/env bash
# C2 client wrapper on apt138. Compile once:  bash load.sh compile
J=$HOME/cassandra-c1/build/lib/jars
CP="/mydata/c2/loadcls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$HOME/cassandra-c1/lib/*"
if [ "$1" = compile ]; then mkdir -p /mydata/c2/loadcls; exec javac -cp "$CP" -d /mydata/c2/loadcls /mydata/c2/harness/C2Load.java; fi
exec java -Xmx8g -XX:MaxDirectMemorySize=4g -cp "$CP" -Dlogback.configurationFile=/mydata/c2/harness/logback-load.xml C2Load "$@"
