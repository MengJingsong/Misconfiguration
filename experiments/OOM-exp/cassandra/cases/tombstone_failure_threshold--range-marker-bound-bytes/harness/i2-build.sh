#!/usr/bin/env bash
# B16 arm I2 diagnostic build (separate tree): the two marker classes with unsharedHeapSize() counting the bound
# (exact diff: harness/i2.diff); compiled against the unmodified jar and written into a copy of it.
set -euo pipefail
ROOT=/mydata/s4/b16-w4
[ -d $ROOT/tree-i2 ] || cp -a $ROOT/tree $ROOT/tree-i2
rm -rf $ROOT/i2cls; mkdir -p $ROOT/i2cls
T=$ROOT/tree
javac -nowarn -d $ROOT/i2cls -cp "$T/build/apache-cassandra-5.0.9-SNAPSHOT.jar:$T/lib/*:$T/build/lib/jars/*" \
  $ROOT/i2src/org/apache/cassandra/db/rows/RangeTombstoneBoundMarker.java $ROOT/i2src/org/apache/cassandra/db/rows/RangeTombstoneBoundaryMarker.java
ls -R $ROOT/i2cls | grep class
(cd $ROOT/i2cls && jar uf $ROOT/tree-i2/build/apache-cassandra-5.0.9-SNAPSHOT.jar org)
sha256sum $ROOT/tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar $ROOT/tree-i2/build/apache-cassandra-5.0.9-SNAPSHOT.jar
