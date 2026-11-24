#!/usr/bin/env bash
# 3-b confirm C10 setup on pc91: copy the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), pristine conf,
# compile the attack client, victim client and sampler. Harness is scp'd to $ROOT/harness beforehand.
set -euo pipefail
ROOT=/mydata/s4/3b-C10
mkdir -p "$ROOT"/{runs,cls,logs} /dev/shm/3b-c10
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/C10Load.java" "$ROOT/harness/C10Sampler.java" "$ROOT/harness/C10Victim.java"
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar
echo setup ok
