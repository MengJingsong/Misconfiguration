#!/usr/bin/env bash
# U8 setup on ms0640 (stage 2). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), keeps a
# pristine conf, compiles the client, the sampler and the arm-I diagnostic VectorType (one method changed; diff in
# vectortype-intervention.diff). The harness directory is copied to $ROOT/harness by the controller (rsync) first.
set -euo pipefail
ROOT=/mydata/s4/u8-w4
mkdir -p "$ROOT"/{runs,out,cls,patch}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/U8Client.java" "$ROOT/harness/C2Sampler.java"
javac --release 11 -nowarn -cp "$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*:$ROOT/tree/build/lib/jars/*" \
  -d "$ROOT/patch" "$ROOT/harness/VectorType.java" 2>&1 | grep -v '^Note:' || true
ls "$ROOT"/patch/org/apache/cassandra/db/marshal/VectorType*.class
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar "$ROOT"/patch/org/apache/cassandra/db/marshal/VectorType*.class
echo setup ok
