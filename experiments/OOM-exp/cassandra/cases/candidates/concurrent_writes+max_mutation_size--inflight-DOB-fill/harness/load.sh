#!/usr/bin/env bash
# Wrapper for U1Load / U1Sample (compiled into /mydata/u1/cls by build.sh). Client and sampler pinned to cores 24-31.
J=/mydata/b6/cassandra/build/lib/jars
CP="/mydata/u1/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:/mydata/b6/cassandra/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  sample) shift; exec taskset -c 24-31 java -Xmx256m -cp "$CP" U1Sample "$@" ;;
  *) exec taskset -c 24-31 java -Xmx6g ${JOPTS:-} -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml U1Load "$@" ;;
esac
