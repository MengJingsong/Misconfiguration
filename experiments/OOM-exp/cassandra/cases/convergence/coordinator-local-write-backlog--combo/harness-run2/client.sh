#!/usr/bin/env bash
# S2 run 2 client wrapper on ms0617.  client.sh build | client.sh load <args of S2Load>   (env CL, REPL)
B=/mydata/s2r2/cassandra; J=$B/build/lib/jars
CP="/mydata/s2r2/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$B/lib/*:$J/*"
c=$1; shift
case $c in
  build) mkdir -p /mydata/s2r2/cls; javac -cp "$CP" -d /mydata/s2r2/cls /mydata/s2r2/h/S2Load.java /mydata/s2r2/h/S2Poll.java ;;
  load) RP=(); [ -n "${REPL:-}" ] && RP=("-Drepl=$REPL")
        exec java -Xmx4g -Dcl=${CL:-ONE} "${RP[@]}" -cp "$CP" -Dlogback.configurationFile=/mydata/s2r2/h/logback-load.xml S2Load "$@" ;;
esac
