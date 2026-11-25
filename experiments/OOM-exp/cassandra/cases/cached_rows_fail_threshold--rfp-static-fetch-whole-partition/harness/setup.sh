#!/usr/bin/env bash
# B29 setup on pc72 (stage 2, 2026-11-24), adapted from B22's setup.sh. Copies the built 5.0.9 tree out of
# /mydata/s4/cassandra-base (read only), keeps a pristine conf, compiles the client, sampler and JMX helper, and builds the
# arm-I tree ($ROOT/tree-I): I-names.diff applied to a copy of the source, ReplicaFilteringProtection*.class recompiled
# against the shipped classes and swapped into a copy of the shipped jar (no other class changes). Byteman script checked.
set -euo pipefail
ROOT=/mydata/s4/b29; H=$ROOT/harness
mkdir -p "$ROOT"/{runs,cls}
[ -d "$ROOT/tree" ] || cp -a /mydata/s4/cassandra-base "$ROOT/tree"
[ -d "$ROOT/conf-pristine" ] || cp -a "$ROOT/tree/conf" "$ROOT/conf-pristine"
J=$ROOT/tree/build/lib/jars
CP="$J/cassandra-driver-core-3.12.1-shaded.jar:$J/guava-32.0.1-jre.jar:$J/metrics-core-4.2.28.jar:$ROOT/tree/lib/*"
javac -cp "$CP" -d "$ROOT/cls" "$H/B29Load.java" "$H/B29Sampler.java" "$H/RfpJmx.java"
# arm I tree
if [ ! -d "$ROOT/tree-I" ]; then
  cp -a "$ROOT/tree" "$ROOT/tree-I"
  ( cd "$ROOT/tree-I" && patch -p1 < "$H/I-names.diff" )
  mkdir -p "$ROOT/tree-I/patch-cls"
  javac -nowarn -d "$ROOT/tree-I/patch-cls" -cp "$ROOT/tree/build/classes/main:$J/*:$ROOT/tree/lib/*" \
    "$ROOT/tree-I/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java" 2>&1 | grep -v '^Note:' || true
  ( cd "$ROOT/tree-I/patch-cls" && jar uf "$ROOT/tree-I/build/apache-cassandra-5.0.9-SNAPSHOT.jar" org/apache/cassandra/service/reads/ReplicaFilteringProtection*.class )
  cp "$ROOT/tree-I/patch-cls"/org/apache/cassandra/service/reads/ReplicaFilteringProtection*.class "$ROOT/tree-I/build/classes/main/org/apache/cassandra/service/reads/"
  ls "$ROOT/tree-I/patch-cls/org/apache/cassandra/service/reads/"
fi
( cd "$ROOT/tree-I" && diff -u "$ROOT/tree/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java" src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java ) || true
java -cp "$J/byteman-4.0.20.jar:$ROOT/tree/build/classes/main:$J/*:$ROOT/tree/lib/*" org.jboss.byteman.check.TestScript "$H/b29.btm" 2>&1 | tail -3
sha256sum "$ROOT"/tree/build/apache-cassandra-*.jar "$ROOT"/tree-I/build/apache-cassandra-*.jar
echo setup ok
