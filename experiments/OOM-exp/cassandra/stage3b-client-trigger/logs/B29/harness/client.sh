#!/usr/bin/env bash
# 3-b confirm B29: client wrapper. client.sh <role> <Class> <args...>; role in cassandra|attacker|victim|nogrant|none.
# Client JVM in its own scope (isolation only), as stage 2's client.sh.
ROOT=/mydata/s4/3b-B29; J=$ROOT/tree/build/lib/jars; ROLE=$1; CLS=$2; shift 2
case $ROLE in cassandra) PW=cassandra;; attacker) PW=att-pw;; victim) PW=vic-pw;; nogrant) PW=nog-pw;; *) PW=;; esac
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
CR=""; [ "$ROLE" != none ] && CR="-Db29.user=$ROLE -Db29.pass=$PW -Dc10.user=$ROLE -Dc10.pass=$PW"
exec systemd-run --user --scope --quiet --unit="3bb29-cl-$ROLE-$(date +%s%N | cut -c1-13)" -p MemorySwapMax=0 \
  java -Xmx2g $CR -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml "$CLS" "$@"
