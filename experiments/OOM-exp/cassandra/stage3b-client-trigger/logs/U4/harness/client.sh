#!/usr/bin/env bash
# 3-b confirm U4 client wrapper (pc91, loopback): role from U4USER/U4PASS (unset = no credentials). Own scope (isolation only).
#   client.sh <label> <U4Load|U4Victim> <args...>
ROOT=/mydata/s4/3b-U4; J=$ROOT/tree/build/lib/jars; L=$1; CLS=$2; shift 2
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
XMX=-Xmx16g; [ "$CLS" = U4Victim ] && XMX=-Xmx1g
CRED=""; [ -n "${U4USER:-}" ] && CRED="-Du4.user=$U4USER -Du4.pass=${U4PASS:-}"
exec systemd-run --user --scope --quiet --unit="3bu4-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=40G -p MemorySwapMax=0 \
  java $XMX -XX:MaxDirectMemorySize=16g -cp "$CP" $CRED -Dlogback.configurationFile=$ROOT/harness/logback-load.xml "$CLS" "$@"
