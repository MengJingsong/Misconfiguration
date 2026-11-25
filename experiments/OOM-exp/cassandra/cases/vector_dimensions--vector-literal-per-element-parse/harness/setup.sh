#!/usr/bin/env bash
# U17 setup on pc75 (stage 2). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only), keeps a
# pristine conf, compiles the JMX sampler and the arm-I/WI diagnostic QueryMessage (one method wrapped; diff in
# querymessage-intervention.diff). The harness directory is copied to $ROOT/harness by the controller (rsync) first.
set -euo pipefail
ROOT=/mydata/s4/u17
mkdir -p "$ROOT"/{runs,out,cls,patch}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
javac -d "$ROOT/cls" "$ROOT/harness/C2Sampler.java"
javac --release 11 -nowarn -cp "$ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$ROOT/tree/lib/*:$ROOT/tree/build/lib/jars/*" \
  -d "$ROOT/patch" "$ROOT/harness/QueryMessage.java" 2>&1 | grep -v '^Note:' || true
ls "$ROOT"/patch/org/apache/cassandra/transport/messages/QueryMessage*.class
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar "$ROOT"/tree/lib/antlr-runtime-*.jar "$ROOT"/patch/org/apache/cassandra/transport/messages/QueryMessage*.class
python3 -I "$ROOT/harness/u17client.py" --sizes --d 6000000
python3 -I "$ROOT/harness/u17client.py" --sizes --d 500000
echo setup ok
