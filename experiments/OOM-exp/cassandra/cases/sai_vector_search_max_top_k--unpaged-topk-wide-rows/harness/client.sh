#!/usr/bin/env bash
# B21 client wrapper (ms0604, loopback). Client JVM (6 GiB heap) in its own scope, swap off.  client.sh <label> <B21Load args...>
ROOT=/mydata/s4/b21; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="b21-client-$L-$(date +%s%N | cut -c1-13)" -p MemorySwapMax=0 \
  java -Xmx6g -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml B21Load "$@"
