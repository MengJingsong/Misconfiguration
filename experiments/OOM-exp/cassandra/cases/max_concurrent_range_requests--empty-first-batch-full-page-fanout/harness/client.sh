#!/usr/bin/env bash
# C10 client wrapper (pc91, loopback). Client JVM pinned to CPUs 30-31, own scope (isolation only).  client.sh <label> <C10Load args...>
ROOT=/mydata/s4/c10; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*"
exec taskset -c 30-31 systemd-run --user --scope --quiet --unit="c10-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=40G -p MemorySwapMax=0 \
  java -Xmx16g -XX:MaxDirectMemorySize=16g -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml C10Load "$@"
