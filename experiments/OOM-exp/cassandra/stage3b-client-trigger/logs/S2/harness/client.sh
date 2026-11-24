#!/usr/bin/env bash
# 3-b confirm S2 (pc91) client wrapper: java clients pinned to the client threads (no scope). Role from env S2USER/S2PASS
# (attacker / admin / probes) and S2VUSER/S2VPASS (victim); CL from env CL (S2Load, default ONE).
#   client.sh <class> <args...>
ROOT=/mydata/s4/3b-S2; J=$ROOT/tree/build/lib/jars
CP="$ROOT/cls:$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*:$J/*"
CLS=$1; shift
exec taskset -c 9,11,13,15,25,27,29,31 java -Xmx4g -Ds2.user="${S2USER:-}" -Ds2.pass="${S2PASS:-}" -Ds2v.user="${S2VUSER:-}" -Ds2v.pass="${S2VPASS:-}" \
  -Dcl="${CL:-ONE}" -Ds2.cl="${S2CL:-ONE}" -cp "$CP" -Dlogback.configurationFile=$ROOT/harness/logback-load.xml $CLS "$@"
