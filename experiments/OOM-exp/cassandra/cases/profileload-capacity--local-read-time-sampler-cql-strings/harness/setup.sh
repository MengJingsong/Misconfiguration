#!/usr/bin/env bash
# B26 setup on pc91 (stage 2). Copies the built 5.0.9 tree out of /mydata/s4/cassandra-base (read only) to tree (build A)
# and tree-iv (build IV: iv.patch applied; ReadExecutionController recompiled with javac and the jar updated with
# `jar uf`, no ant), keeps a pristine conf, copies this harness to the node, compiles the client and the JMX sampler.
set -euo pipefail
ROOT=/mydata/s4/b26
SRC=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
rm -rf "$ROOT/harness"; cp -r "$SRC" "$ROOT/harness"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$ROOT/harness/B26Load.java" "$ROOT/harness/C2Sampler.java"
if [ ! -f "$ROOT/tree-iv/.iv-built" ]; then
  rm -rf "$ROOT/tree-iv"; cp -a /mydata/s4/cassandra-base "$ROOT/tree-iv"
  cd "$ROOT/tree-iv"
  patch -p1 < "$ROOT/harness/iv.patch"
  T=$ROOT/tree-iv
  mkdir -p "$ROOT/iv-cls"
  javac -nowarn -source 11 -target 11 -encoding utf-8 -cp "$T/build/classes/main:$T/build/lib/jars/*:$T/lib/*" -d "$ROOT/iv-cls" \
    src/java/org/apache/cassandra/db/ReadExecutionController.java 2>&1 | grep -v '^Note:' || true
  ls "$ROOT/iv-cls/org/apache/cassandra/db/"ReadExecutionController*.class
  cp "$ROOT"/iv-cls/org/apache/cassandra/db/ReadExecutionController*.class "$T/build/classes/main/org/apache/cassandra/db/"
  ( cd "$ROOT/iv-cls" && jar uf "$T"/build/apache-cassandra-5.0.9-SNAPSHOT.jar org/apache/cassandra/db/ReadExecutionController*.class )
  touch "$T/.iv-built"
fi
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar "$ROOT"/tree-iv/build/apache-cassandra-*.jar
echo setup ok
