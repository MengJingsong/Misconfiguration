#!/usr/bin/env bash
# Wrapper for C1Load / C1Sample (compiled into /mydata/c1r4/cls by build.sh).
J=/mydata/b6/cassandra/build/lib/jars
CP="/mydata/c1r4/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  sample) shift; exec taskset -c 24-31 java -Xmx512m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml C1Sample "$@" ;;
  *) exec taskset -c 24-31 java -Xmx4g -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml C1Load "$@" ;;
esac
