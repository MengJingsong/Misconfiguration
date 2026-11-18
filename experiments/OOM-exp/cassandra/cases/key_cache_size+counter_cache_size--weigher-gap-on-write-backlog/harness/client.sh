#!/usr/bin/env bash
# R8 client wrapper on pc91 (from S2 run-2 client.sh). Pinned to NUMA node1 CPUs (1-31:2).
#   client.sh build | client.sh load <args of S2Load> (env N = total writes) | client.sh fill <args of S2CacheFill>
W=/mydata/s4/r8-w1; B=$W/run-orig; J=$B/build/lib/jars
CP="$W/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$B/lib/*:$J/*"
c=$1; shift
case $c in
  build) mkdir -p $W/cls; javac -cp "$CP" -d $W/cls $W/h/S2Load.java $W/h/S2CacheFill.java $W/h/S2Poll.java ;;
  load) TT=(); [ -n "${N:-}" ] && TT=("-Dtotal=$N")
        exec taskset -c 1-31:2 java -Xmx4g -Dcl=${CL:-ONE} "${TT[@]}" -cp "$CP" -Dlogback.configurationFile=$W/h/logback-load.xml S2Load "$@" ;;
  fill) exec taskset -c 1-31:2 java -Xmx2g -cp "$CP" -Dlogback.configurationFile=$W/h/logback-load.xml -Dhost=127.0.0.2 -Dks=s2c S2CacheFill "$@" ;;
esac
