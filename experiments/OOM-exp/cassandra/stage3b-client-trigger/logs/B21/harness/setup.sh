#!/usr/bin/env bash
# B21 3-b confirm setup on pc72 (2026-11-23; stage 2 setup.sh with ROOT /mydata/s4/3b-B21 and the two new classes).
# pristine conf, copies this harness to the node and compiles the client and the sampler.
set -euo pipefail
ROOT=/mydata/s4/3b-B21
SRC=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
# the harness is rsynced from the scratch copy to $ROOT/harness
[ "$SRC" = "$ROOT/harness" ] || { rm -rf "$ROOT/harness"; cp -r "$SRC" "$ROOT/harness"; }
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/B21Load.java" "$ROOT/harness/AuthCheck.java" "$ROOT/harness/B21Victim.java" "$ROOT/harness/C2Sampler.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
