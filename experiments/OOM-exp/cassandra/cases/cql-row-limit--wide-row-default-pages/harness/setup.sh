#!/usr/bin/env bash
# U4 setup on pc75 (stage 2). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), keeps a
# pristine conf, copies this harness to the node and compiles the client and the sampler.
set -euo pipefail
ROOT=/mydata/s4/u4-w1
SRC=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
rm -rf "$ROOT/harness"; cp -r "$SRC" "$ROOT/harness"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/U4Load.java" "$ROOT/harness/C2Sampler.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
