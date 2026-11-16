#!/usr/bin/env bash
# Wrapper for S1Load / S1Sample (compiled into /mydata/s1/cls by build.sh).
J=/mydata/b6/cassandra/build/lib/jars
CP="/mydata/s1/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  sample) shift; exec taskset -c 24-31 java -Xmx512m -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml S1Sample "$@" ;;
  *) exec taskset -c 24-31 java -Xmx4g ${JOPTS:-} -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml S1Load "$@" ;;
esac
