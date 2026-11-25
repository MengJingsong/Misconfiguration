#!/usr/bin/env bash
# 3-b confirm U4 setup on pc91 (2026-11-24). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only),
# keeps a pristine conf, and compiles the clients and the sampler. Harness is copied to $ROOT/harness beforehand.
set -euo pipefail
ROOT=/mydata/s4/3b-U4
mkdir -p "$ROOT"/{runs,cls,logs}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/U4Load.java" "$ROOT/harness/U4Victim.java" "$ROOT/harness/C2Sampler.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
