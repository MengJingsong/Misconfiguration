#!/usr/bin/env bash
# U10 client wrapper (pc82, loopback). Client JVM -Xmx4g in its own scope (MemoryMax=8G, isolation only).  load.sh <label> <U10Load args...>
ROOT=/mydata/s4/u10-w4; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="u10-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=8G -p MemorySwapMax=0 \
  java -Xmx4g -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml U10Load "$@"
