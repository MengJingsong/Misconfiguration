#!/usr/bin/env bash
# B16 3-b confirm setup on ms0611 (2026-11-23; stage-2 setup.sh with ROOT /mydata/s4/3b-B16 and the victim class).
# The build /mydata/s4/cassandra-base (copied from ms0617 in stage 2; base left read-only) is copied to the work root;
# pristine conf; the harness is rsynced to $ROOT/harness first; compile the clients and the sampler.
set -euo pipefail
ROOT=/mydata/s4/3b-B16
mkdir -p "$ROOT"/{runs,cls,out}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/B16Load.java" "$ROOT/harness/B16Victim.java" "$ROOT/harness/C2Sampler.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
