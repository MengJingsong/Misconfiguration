#!/usr/bin/env bash
# B17 3-b confirm client wrapper (pc75, loopback; from stage 2's client.sh). The client JVM runs in its own scope (swap off)
# and logs in as <role> through the native protocol (env B17_USER / B17_PASS -> PlainTextAuthProvider).
#   client.sh <label> <role|none> <Class: B17Load|B17Victim|B17Auth> <args...>
#   roles: cassandra (superuser: admin-setup only), attacker (data role), tenant (victim role), reader (SELECT-only check)
ROOT=/mydata/s4/3b-B17; J=$ROOT/tree/build/lib/jars; L=$1; ROLE=$2; CLS=$3; shift 3
case $ROLE in
  cassandra) P=cassandra;; attacker) P=atk-3b-B17;; tenant) P=ten-3b-B17;; reader) P=rd-3b-B17;;
  none) ROLE=""; P="";; *) echo "unknown role $ROLE" >&2; exit 2;;
esac
XMX=-Xmx4g; [ "$CLS" = B17Victim ] && XMX=-Xmx512m
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
export B17_USER=$ROLE B17_PASS=$P
exec systemd-run --user --scope --quiet --unit="b3b17-client-$L-$(date +%s%N | cut -c1-13)" -p MemorySwapMax=0 \
  java $XMX -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml $CLS "$@"
