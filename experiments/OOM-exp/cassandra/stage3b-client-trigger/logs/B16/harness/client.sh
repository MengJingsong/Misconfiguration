#!/usr/bin/env bash
# B16 3-b confirm client wrapper (ms0611, loopback; from stage 2's load.sh and B21 3-b's client.sh). The client JVM runs in
# its own scope (swap off) and logs in as <role> through the native protocol (env B16_USER / B16_PASS).
#   client.sh <label> <role|none> <Class: B16Load|B16Victim> <args...>
#   roles: cassandra (superuser: admin-setup only), attacker (SELECT+MODIFY on b16.t, b16.m), tenant (victim: SELECT+MODIFY
#   on vic.kv), reader (SELECT on b16.t; claim checks only)
ROOT=/mydata/s4/3b-B16; J=$ROOT/tree/build/lib/jars; L=$1; ROLE=$2; CLS=$3; shift 3
case $ROLE in
  cassandra) P=cassandra;; attacker) P=atk-3b-B16;; tenant) P=ten-3b-B16;; reader) P=rd-3b-B16;;
  none) ROLE=""; P="";; *) echo "unknown role $ROLE" >&2; exit 2;;
esac
XMX=-Xmx2g; MM=6G; [ "$CLS" = B16Victim ] && { XMX=-Xmx512m; MM=2G; }
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
export B16_USER=$ROLE B16_PASS=$P
exec systemd-run --user --scope --quiet --unit="b3b16-client-$L-$(date +%s%N | cut -c1-13)" -p MemoryMax=$MM -p MemorySwapMax=0 \
  java $XMX -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml $CLS "$@"
