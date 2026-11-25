#!/usr/bin/env bash
# R24 I-patch diagnostic build (design §2.7): copy of the built tree, the one-line i-patch.diff to ReplicaFilteringProtection.java,
# `ant jar` offline. Output: $ROOT/tree-patched, with the jar's sha256.
set -euo pipefail
ROOT=/mydata/s4/r24
rm -rf "$ROOT/tree-patched"; cp -a "$ROOT/tree" "$ROOT/tree-patched"
cd "$ROOT/tree-patched"
patch -p1 < "$ROOT/harness/i-patch.diff"
grep -n 'this.consumeEntirePartitions =' src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java
time ant -Doffline=true jar
sha256sum build/apache-cassandra-*.jar
echo build-patched ok
