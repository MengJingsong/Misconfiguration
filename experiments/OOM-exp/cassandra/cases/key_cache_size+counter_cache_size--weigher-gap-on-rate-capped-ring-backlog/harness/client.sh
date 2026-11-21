#!/usr/bin/env bash
# R19 client wrapper (R11 client.sh): runs on ms0604 (load, fill); `build` on every node; gate (logger only) on V.
#   client.sh build | client.sh load <args of S2Load> (env CL, TOTAL=N) | client.sh fill <args of S2CacheFill> | client.sh gate 0 <port> <log>
W=/mydata/r19; B=$W/run-orig; J=$B/build/lib/jars
CP="$W/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$B/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$B/lib/*:$J/*"
VR=3074457345618258602
c=$1; shift
case $c in
  build) mkdir -p $W/cls; javac -cp "$CP" -d $W/cls $W/h/S2Load.java $W/h/S2CacheFill.java $W/h/S2Poll.java $W/h/R11Gate.java ;;
  load) GT=(); [ -n "${GATE:-}" ] && GT=("-Dgate=$GATE"); [ -n "${TOTAL:-}" ] && GT+=("-Dtotal=$TOTAL")
        exec java -Xmx4g -Dcl=${CL:-ONE} "${GT[@]}" -cp "$CP" -Dlogback.configurationFile=$W/h/logback-load.xml S2Load "$@" ;;
  fill) exec java -Xmx2g -cp "$CP" -Dlogback.configurationFile=$W/h/logback-load.xml -Dhost=10.10.1.4 -Dvip=10.10.1.4 -Dks=s2c -Dvrange=$VR S2CacheFill "$@" ;;
  gate) exec nice -n 10 java -Xmx32m -cp $W/cls R11Gate "$@" ;;
esac
