#!/usr/bin/env bash
# Wrapper for B9Load / B9Sample (compiled into /mydata/s4/b9-w1/cls by build.sh). Client, sampler pinned to cores 6-7.
B=/mydata/s4/cassandra-base; J=$B/build/lib/jars
CP="/mydata/s4/b9-w1/cls:$J/*:$B/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  sample) shift; exec taskset -c 6-7 java -Xmx256m -cp "$CP" B9Sample "$@" ;;
  *) exec taskset -c 6-7 java -Xmx6g -XX:MaxDirectMemorySize=16g ${JOPTS:-} -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml B9Load "$@" ;;
esac
