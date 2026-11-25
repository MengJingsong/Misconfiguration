#!/usr/bin/env bash
# Wrapper for B8Load. Compiled once into /mydata/s4/r23/loadcls by:  load.sh --compile
J=/mydata/s4/r23/cassandra/build/lib/jars
CP="/mydata/s4/r23/loadcls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/s4/r23/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
if [ "$1" = --compile ]; then mkdir -p /mydata/s4/r23/loadcls; exec javac -cp "$CP" -d /mydata/s4/r23/loadcls "$H/B8Load.java"; fi
exec java -Xmx2g -cp "$CP" -Dlogback.configurationFile=$H/logback-load.xml B8Load "$@"
