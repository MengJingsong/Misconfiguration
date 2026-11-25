#!/usr/bin/env bash
# R24 setup on pc82 (stage 2, 2026-11-24), adapted from B22's setup.sh. Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base
# (read only), keeps a pristine conf, compiles the client, sampler, JMX helper and the DIAG probe jar (harness rsynced from the repo first).
set -euo pipefail
ROOT=/mydata/s4/r24
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/R24Load.java" "$ROOT/harness/R24Sampler.java" "$ROOT/harness/RfpJmx.java"
mkdir -p "$ROOT/cls-probe"
javac -d "$ROOT/cls-probe" -cp "$ROOT/tree/build/classes/main:$J/*:$ROOT/tree/lib/*" "$ROOT/harness/stage4/rfp/RfpProbe.java"
( cd "$ROOT/cls-probe" && jar cf "$ROOT/cls/rfp-helper.jar" stage4 )
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
