#!/usr/bin/env bash
# B16 client wrapper (ms0611, loopback). Client JVM in its own scope (isolation only).  load.sh <label> <B16Load args...>
ROOT=/mydata/s4/b16-w4; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="b16-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=6G -p MemorySwapMax=0 \
  java -Xmx2g -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml B16Load "$@"
