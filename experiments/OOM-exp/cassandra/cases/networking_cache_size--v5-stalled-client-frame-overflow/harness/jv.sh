#!/usr/bin/env bash
# Wrapper for B13Sample / B13Load (classes in /mydata/s4/b13-w3/cls). Pinned to cores 6-7.
B=/mydata/s4/cassandra-base; J=$B/build/lib/jars
CP="/mydata/s4/b13-w3/cls:$J/*:$B/lib/*"
H=$(cd "$(dirname "$0")" && pwd)
case "$1" in
  sample) shift; exec taskset -c 6-7 java -Xmx256m -cp "$CP" B13Sample "$@" ;;
  load) shift; exec taskset -c 6-7 java -Xmx1g -cp "$CP" -Dlogback.configurationFile=$H/logback-quiet.xml B13Load "$@" ;;
esac
