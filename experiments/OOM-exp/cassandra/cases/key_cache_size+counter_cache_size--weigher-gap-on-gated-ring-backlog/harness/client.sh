#!/usr/bin/env bash
# R11 client wrapper (from S2 run-2 / R8 client.sh). Runs on ms0617 (load, fill); `build` on every node.
#   client.sh build | client.sh load <args of S2Load> (env GATE=host:port, CL) | client.sh fill <args of S2CacheFill>
#   | client.sh gate <G> <port> <log>  (on V)
W=/mydata/r11; B=$W/run-orig; J=$B/build/lib/jars
CP="$W/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$B/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$B/lib/*:$J/*"
VR=3074457345618258602
c=$1; shift
case $c in
  build) mkdir -p $W/cls; javac -cp "$CP" -d $W/cls $W/h/S2Load.java $W/h/S2CacheFill.java $W/h/S2Poll.java $W/h/R11Gate.java ;;
  load) GT=(); [ -n "${GATE:-}" ] && GT=("-Dgate=$GATE")
        exec java -Xmx4g -Dcl=${CL:-ONE} "${GT[@]}" -cp "$CP" -Dlogback.configurationFile=$W/h/logback-load.xml S2Load "$@" ;;
  fill) exec java -Xmx2g -cp "$CP" -Dlogback.configurationFile=$W/h/logback-load.xml -Dhost=10.10.1.4 -Dvip=10.10.1.4 -Dks=s2c -Dvrange=$VR S2CacheFill "$@" ;;
  gate) exec nice -n 10 java -Xmx32m -cp $W/cls R11Gate "$@" ;;
esac
