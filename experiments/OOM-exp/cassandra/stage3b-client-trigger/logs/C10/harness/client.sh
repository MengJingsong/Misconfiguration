#!/usr/bin/env bash
# 3-b confirm C10 client wrapper (pc91, loopback): as stage 2's, plus the role from env C10USER / C10PASS (unset = no
# credentials), C10KS / C10CL (keyspace of the attack table, CL; default c10 / ONE). Client JVM pinned to CPUs 30-31, own scope (isolation only).  client.sh <label> <class> <args...>
ROOT=/mydata/s4/3b-C10; J=$ROOT/tree/build/lib/jars; L=$1; CLS=$2; shift 2
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*"
exec taskset -c 30-31 systemd-run --user --scope --quiet --unit="3bc10-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=40G -p MemorySwapMax=0 \
  java -Xmx16g -XX:MaxDirectMemorySize=16g -Dc10.user="${C10USER:-}" -Dc10.pass="${C10PASS:-}" -Dc10.ks="${C10KS:-c10}" -Dc10.cl="${C10CL:-ONE}" -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml $CLS "$@"
