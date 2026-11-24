#!/usr/bin/env bash
# U10 client wrapper (ms0640, loopback; 3-b confirm). Client JVM -Xmx2g in its own scope (MemoryMax=4G, isolation only).
#   load.sh <label> <role: su|atk|vic|none|<user>:<pass>> <U10Load args...>    (u10.parts from $U10_PARTS, default 2)
ROOT=/mydata/s4/3b-U10; J=$ROOT/tree/build/lib/jars; L=$1; ROLE=$2; shift 2
case $ROLE in su) U=cassandra; P=cassandra;; atk) U=u10atk; P=atk-3bU10;; vic) U=u10victim; P=vic-3bU10;; none) U=; P=;; *) U=${ROLE%%:*}; P=${ROLE#*:};; esac
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="3bu10-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=4G -p MemorySwapMax=0 \
  java -Xmx2g -cp "$CP" -Du10.user="$U" -Du10.pass="$P" -Du10.parts=${U10_PARTS:-2} -Dlogback.configurationFile=$ROOT/harness/logback-load.xml U10Load "$@"
