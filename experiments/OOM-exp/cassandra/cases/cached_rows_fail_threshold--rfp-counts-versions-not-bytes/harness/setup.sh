#!/usr/bin/env bash
# B22 setup on pc82 (stage 2). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), keeps a pristine conf,
# copies this harness to the node (rsync from the repo first), compiles the client, sampler, JMX helper and the DIAG probe jar.
set -euo pipefail
ROOT=/mydata/s4/b22
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/B22Load.java" "$ROOT/harness/B22Sampler.java" "$ROOT/harness/RfpJmx.java"
mkdir -p "$ROOT/cls-probe"
javac -d "$ROOT/cls-probe" -cp "$ROOT/tree/build/classes/main:$J/*:$ROOT/tree/lib/*" "$ROOT/harness/stage4/rfp/RfpProbe.java"
( cd "$ROOT/cls-probe" && jar cf "$ROOT/cls/rfp-helper.jar" stage4 )
java -cp "$J/byteman-4.0.20.jar:$ROOT/cls/rfp-helper.jar:$ROOT/tree/build/classes/main:$J/*:$ROOT/tree/lib/*" org.jboss.byteman.check.TestScript "$ROOT/harness/rfp.btm" 2>&1 | tail -2
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
