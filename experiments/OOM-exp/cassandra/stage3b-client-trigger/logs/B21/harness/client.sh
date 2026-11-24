#!/usr/bin/env bash
# B21 3-b confirm client wrapper (pc72, loopback; adapted from stage 2's client.sh). The client JVM runs in its own scope
# (swap off) and logs in as <role> through the native protocol (env B21_USER / B21_PASS -> PlainTextAuthProvider).
#   client.sh <label> <role|none> <Class: B21Load|B21Victim> <args...>
#   roles: cassandra (superuser: admin-setup only), attacker, tenant (victim role), reader, ddl, ddlks (claim checks)
ROOT=/mydata/s4/3b-B21; J=$ROOT/tree/build/lib/jars; L=$1; ROLE=$2; CLS=$3; shift 3
case $ROLE in
  cassandra) P=cassandra;; attacker) P=atk-3b-B21;; tenant) P=ten-3b-B21;; reader) P=rd-3b-B21;;
  ddl) P=ddl-3b-B21;; ddlks) P=ddlks-3b-B21;; none) ROLE=""; P="";; *) echo "unknown role $ROLE" >&2; exit 2;;
esac
XMX=-Xmx6g; [ "$CLS" = B21Victim ] && XMX=-Xmx512m
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
export B21_USER=$ROLE B21_PASS=$P
exec systemd-run --user --scope --quiet --unit="b3b21-client-$L-$(date +%s%N | cut -c1-13)" -p MemorySwapMax=0 \
  java $XMX -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml $CLS "$@"
