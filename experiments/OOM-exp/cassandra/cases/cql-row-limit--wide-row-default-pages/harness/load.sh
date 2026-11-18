#!/usr/bin/env bash
# U4 client wrapper (pc75, loopback). Client JVM in its own scope (isolation only).  load.sh <label> <U4Load args...>
ROOT=/mydata/s4/u4-w1; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="u4-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=40G -p MemorySwapMax=0 \
  java -Xmx16g -XX:MaxDirectMemorySize=16g -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml U4Load "$@"
