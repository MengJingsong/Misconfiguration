#!/usr/bin/env bash
# B17 client wrapper (pc72, loopback). Client JVM (4 GiB heap) in its own scope, swap off.  client.sh <label> <B17Load args...>
ROOT=/mydata/s4/b17-w4; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="b17-client-$L-$(date +%s%N | cut -c1-13)" -p MemorySwapMax=0 \
  java -Xmx4g -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml B17Load "$@"
