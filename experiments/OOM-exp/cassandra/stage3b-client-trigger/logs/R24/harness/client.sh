#!/usr/bin/env bash
# 3-b R24 client wrapper (from stage 2's client.sh): JOPTS carries -Dr24.user/-Dr24.pass; class = R24Load unless CLS is set (R24Victim).
ROOT=/mydata/s4/3b-R24; J=$ROOT/tree/build/lib/jars; L=$1; shift
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
exec systemd-run --user --scope --quiet --unit="3br24-client-$L-$(date +%s%N | cut -c1-13)" -p MemorySwapMax=0 \
  java ${XMX:--Xmx8g} ${JOPTS:-} -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml ${CLS:-R24Load} "$@"
