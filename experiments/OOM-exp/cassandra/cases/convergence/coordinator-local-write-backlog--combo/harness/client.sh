#!/usr/bin/env bash
# S2 client wrapper on apt138.  client.sh load <args of S2Load> | client.sh fill <args of S2CacheFill>
J=$HOME/cassandra-c1/build/lib/jars
CP="/mydata/s2/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$HOME/cassandra-c1/lib/*"
c=$1; shift
case $c in
  build) mkdir -p /mydata/s2/cls; javac -cp "$CP" -d /mydata/s2/cls /mydata/s2/h/S2Load.java /mydata/s2/h/S2CacheFill.java ;;
  load) exec java -Xmx4g -Dcl=${CL:-ONE} -cp "$CP" -Dlogback.configurationFile=/mydata/s2/h/logback-load.xml S2Load "$@" ;;
  fill) exec java -Xmx2g -cp "$CP" -Dlogback.configurationFile=/mydata/s2/h/logback-load.xml -Dhost=10.10.1.1 -Dks=s2c S2CacheFill "$@" ;;
esac
